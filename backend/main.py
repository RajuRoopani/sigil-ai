import asyncio
import json
import pathlib
import re
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, FileResponse, HTMLResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request

from config import settings
from analyzer import analyze, analyze_ado

# ── App setup ────────────────────────────────────────────────────────────────

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="AnyRepo-SMEs API", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Persona storage ───────────────────────────────────────────────────────────

PERSONAS_DIR = pathlib.Path(__file__).parent / settings.personas_dir
PERSONAS_DIR.mkdir(exist_ok=True)

# In-memory cache (also backed to disk)
_cache: dict[str, dict] = {}

def _persona_path(cache_key: str) -> pathlib.Path:
    """Sanitise cache_key to a safe directory name."""
    safe = re.sub(r"[^\w\-]", "_", cache_key)
    return PERSONAS_DIR / safe

def _save_persona(cache_key: str, profile: dict) -> pathlib.Path:
    """Persist full profile JSON + identity.md + soul.md to disk."""
    d = _persona_path(cache_key)
    d.mkdir(exist_ok=True)

    # Full profile JSON
    (d / "profile.json").write_text(json.dumps(profile, indent=2, ensure_ascii=False))

    # Agent files
    if profile.get("identity_md"):
        (d / "identity.md").write_text(profile["identity_md"])
    if profile.get("soul_md"):
        (d / "soul.md").write_text(profile["soul_md"])

    # Metadata for listing
    meta = {
        "cache_key": cache_key,
        "username": profile.get("username"),
        "name": profile.get("name"),
        "repo": profile.get("repo"),
        "headline": profile.get("headline"),
        "superpower": profile.get("superpower"),
        "avatar_url": profile.get("avatar_url"),
        "tags": profile.get("tags", []),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "total_commits": profile.get("total_commits", 0),
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=2))
    return d

def _load_all_personas() -> dict[str, dict]:
    """Load all persisted profiles from disk into memory on startup."""
    loaded = {}
    for d in PERSONAS_DIR.iterdir():
        if d.is_dir():
            pf = d / "profile.json"
            if pf.exists():
                try:
                    profile = json.loads(pf.read_text())
                    meta = json.loads((d / "meta.json").read_text())
                    loaded[meta["cache_key"]] = profile
                except Exception:
                    pass
    return loaded

@app.on_event("startup")
async def startup():
    _cache.update(_load_all_personas())
    token = settings.effective_github_token()
    print(f"[startup] Loaded {len(_cache)} persisted personas from disk")
    print(f"[startup] GitHub token: {'✅ present' if token else '❌ missing — set GITHUB_TOKEN or run: gh auth login'}")
    print(f"[startup] Lookback window: {settings.lookback_days} days ({settings.lookback_days//365} year)")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_repo_url(repo_input: str) -> tuple[str, str, str]:
    """
    Returns (source, owner_or_org, repo) where source is 'github' or 'ado'.
    For ADO, owner_or_org is 'org/project' packed together — callers split on '/'.

    Accepted formats:
      GitHub:   owner/repo
                https://github.com/owner/repo
                github.com/owner/repo
                https://github.com/owner/repo.git
      ADO:      https://{org}.visualstudio.com/{project}/_git/{repo}
                https://dev.azure.com/{org}/{project}/_git/{repo}
    """
    repo_input = repo_input.strip().rstrip("/")

    # Internal cache-key format written by this server: ado:{org}/{project}/{repo}
    if repo_input.startswith("ado:"):
        parts = repo_input[4:].split("/")
        if len(parts) == 3:
            return "ado", f"{parts[0]}/{parts[1]}", parts[2]

    # Normalise: add scheme if bare domain given
    if repo_input.startswith("github.com/") or repo_input.startswith("dev.azure.com/"):
        repo_input = "https://" + repo_input

    # Azure DevOps legacy: https://{org}.visualstudio.com/{project}/_git/{repo}
    ado_vs = re.match(
        r"https?://([^.]+)\.visualstudio\.com/([^/]+)/_git/([^/?#]+)",
        repo_input,
    )
    if ado_vs:
        org, project, repo = ado_vs.group(1), ado_vs.group(2), ado_vs.group(3)
        return "ado", f"{org}/{project}", repo.rstrip(".git")

    # Azure DevOps new: https://dev.azure.com/{org}/{project}/_git/{repo}
    ado_new = re.match(
        r"https?://dev\.azure\.com/([^/]+)/([^/]+)/_git/([^/?#]+)",
        repo_input,
    )
    if ado_new:
        org, project, repo = ado_new.group(1), ado_new.group(2), ado_new.group(3)
        return "ado", f"{org}/{project}", repo.rstrip(".git")

    # GitHub full URL
    if "github.com" in repo_input:
        path = re.sub(r"https?://github\.com/", "", repo_input).rstrip("/")
        parts = path.split("/")
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid GitHub URL — expected github.com/owner/repo, got: {repo_input!r}")
        return "github", parts[0], parts[1].removesuffix(".git")

    # owner/repo shorthand
    parts = repo_input.split("/")
    if len(parts) == 2 and parts[0] and parts[1]:
        return "github", parts[0], parts[1].removesuffix(".git")

    raise ValueError(
        f"Unrecognised repo format: {repo_input!r}. "
        "Expected: owner/repo · https://github.com/owner/repo · "
        "https://dev.azure.com/org/project/_git/repo · "
        "https://org.visualstudio.com/project/_git/repo"
    )


# ── Models ────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    repo: str
    username: str
    force_refresh: bool = False     # bypass cache and re-analyze

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    token = settings.effective_github_token()
    from ado_client import _get_ado_token
    ado_token = _get_ado_token()
    return {
        "status": "ok",
        "model": settings.model,
        "github_token": "present" if token else "missing",
        "ado_token": "present" if ado_token else "missing",
        "lookback_days": settings.lookback_days,
        "cached_profiles": len(_cache),
        "personas_dir": str(PERSONAS_DIR),
    }

@app.post("/api/analyze")
@limiter.limit("10/minute")
async def analyze_endpoint(request: Request, body: AnalyzeRequest):
    try:
        source, owner_or_org, repo = _parse_repo_url(body.repo)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if source == "ado":
        org, project = owner_or_org.split("/", 1)
        cache_key = f"ado:{org}/{project}/{repo}::{body.username.lower()}"
    else:
        cache_key = f"{owner_or_org}/{repo}::{body.username.lower()}"

    if cache_key in _cache and not body.force_refresh:
        return {"cache_key": cache_key, "profile": _cache[cache_key], "cached": True}

    try:
        if source == "ado":
            org, project = owner_or_org.split("/", 1)
            profile = await analyze_ado(org, project, repo, body.username)
        else:
            profile = await analyze(owner_or_org, repo, body.username)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {e}")

    _cache[cache_key] = profile
    saved_path = _save_persona(cache_key, profile)
    print(f"[analyze] Saved persona → {saved_path}")

    return {"cache_key": cache_key, "profile": profile, "cached": False, "saved_to": str(saved_path)}

@app.get("/api/profiles")
async def list_profiles():
    result = []
    for cache_key, v in _cache.items():
        # Read saved_at from meta file if available
        meta_file = _persona_path(cache_key) / "meta.json"
        saved_at = None
        if meta_file.exists():
            try:
                saved_at = json.loads(meta_file.read_text()).get("saved_at")
            except Exception:
                pass
        result.append({
            "cache_key": cache_key,
            "username": v.get("username"),
            "name": v.get("name"),
            "repo": v.get("repo"),
            "headline": v.get("headline"),
            "superpower": v.get("superpower"),
            "avatar_url": v.get("avatar_url"),
            "tags": v.get("tags", []),
            "total_commits": v.get("total_commits", 0),
            "saved_at": saved_at,
        })
    return sorted(result, key=lambda x: x.get("saved_at") or "", reverse=True)

@app.get("/api/profiles/{cache_key:path}")
async def get_profile(cache_key: str):
    if cache_key not in _cache:
        raise HTTPException(404, "Profile not found")
    return _cache[cache_key]

@app.delete("/api/profiles/{cache_key:path}")
async def delete_profile(cache_key: str):
    if cache_key not in _cache:
        raise HTTPException(404, "Profile not found")
    _cache.pop(cache_key)
    d = _persona_path(cache_key)
    if d.exists():
        import shutil
        shutil.rmtree(d)
    return {"deleted": cache_key}

@app.get("/api/export/{cache_key:path}/identity.md", response_class=PlainTextResponse)
async def export_identity(cache_key: str):
    if cache_key not in _cache:
        raise HTTPException(404, "Profile not found — run analysis first")
    return PlainTextResponse(
        _cache[cache_key].get("identity_md", ""),
        headers={"Content-Disposition": 'attachment; filename="identity.md"'},
    )

@app.get("/api/export/{cache_key:path}/soul.md", response_class=PlainTextResponse)
async def export_soul(cache_key: str):
    if cache_key not in _cache:
        raise HTTPException(404, "Profile not found — run analysis first")
    return PlainTextResponse(
        _cache[cache_key].get("soul_md", ""),
        headers={"Content-Disposition": 'attachment; filename="soul.md"'},
    )

# ── Serve frontend ────────────────────────────────────────────────────────────

FRONTEND = pathlib.Path(__file__).parent.parent / "frontend"

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    f = FRONTEND / "index.html"
    if f.exists():
        return FileResponse(str(f))
    return HTMLResponse("<h1>Frontend not found</h1>", 404)

@app.get("/pitch", response_class=HTMLResponse)
async def serve_pitch():
    f = FRONTEND / "pitch.html"
    if f.exists():
        return FileResponse(str(f))
    return HTMLResponse("<h1>Pitch deck not found</h1>", 404)
