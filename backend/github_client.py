import httpx
from datetime import datetime, timezone, timedelta
from config import settings

BASE = "https://api.github.com"

def _headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = settings.effective_github_token()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h

def _since_iso() -> str:
    """ISO 8601 timestamp for lookback_days ago."""
    since = datetime.now(timezone.utc) - timedelta(days=settings.lookback_days)
    return since.strftime("%Y-%m-%dT%H:%M:%SZ")

async def get_user(username: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{BASE}/users/{username}", headers=_headers())
        r.raise_for_status()
        return r.json()

async def get_repo(owner: str, repo: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{BASE}/repos/{owner}/{repo}", headers=_headers())
        r.raise_for_status()
        return r.json()

async def get_commits(owner: str, repo: str, author: str) -> list[dict]:
    """Fetch all commits by author in the last `lookback_days` days."""
    since = _since_iso()
    commits = []
    page = 1
    async with httpx.AsyncClient(timeout=25) as c:
        while len(commits) < settings.max_commits:
            r = await c.get(
                f"{BASE}/repos/{owner}/{repo}/commits",
                headers=_headers(),
                params={
                    "author": author,
                    "since": since,
                    "per_page": 100,
                    "page": page,
                },
            )
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            commits.extend(batch)
            page += 1
            if len(batch) < 100:
                break
    return commits[:settings.max_commits]

async def get_commit_detail_json(owner: str, repo: str, sha: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(f"{BASE}/repos/{owner}/{repo}/commits/{sha}", headers=_headers())
        r.raise_for_status()
        return r.json()

async def get_repo_tree(owner: str, repo: str) -> dict:
    """
    Fetch repo directory structure + content of key manifest files.
    Returns {"paths": [...], "key_files": {"package.json": "...", ...}}
    Never raises.
    """
    key_file_names = {
        "package.json", "tsconfig.json", "pyproject.toml",
        "requirements.txt", "go.mod", "Cargo.toml", "README.md",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            # 1. Fetch recursive git tree
            r = await c.get(
                f"{BASE}/repos/{owner}/{repo}/git/trees/HEAD",
                headers=_headers(),
                params={"recursive": "1"},
            )
            paths: list[str] = []
            key_file_paths: list[str] = []
            key_files: dict[str, str] = {}

            if r.status_code == 200:
                for item in r.json().get("tree", []):
                    path = item.get("path", "")
                    if not path:
                        continue
                    paths.append(path)
                    basename = path.split("/")[-1]
                    if basename in key_file_names:
                        key_file_paths.append(path)

            paths = paths[:500]

            # 2. Fetch key file contents
            seen_names: set[str] = set()
            for path in key_file_paths[:8]:
                name = path.split("/")[-1]
                if name in seen_names:
                    continue
                seen_names.add(name)
                try:
                    rf = await c.get(
                        f"{BASE}/repos/{owner}/{repo}/contents/{path}",
                        headers=_headers(),
                    )
                    if rf.status_code == 200:
                        data = rf.json()
                        import base64 as b64
                        if data.get("encoding") == "base64":
                            content = b64.b64decode(data["content"]).decode("utf-8", errors="replace")[:3000]
                        else:
                            content = str(data.get("content", ""))[:3000]
                        key_files[path] = content
                except Exception:
                    pass

            return {"paths": paths, "key_files": key_files}
    except Exception:
        return {"paths": [], "key_files": {}}


async def get_prs(owner: str, repo: str, author: str) -> list[dict]:
    """Fetch PRs authored in the last lookback_days days."""
    since_date = (datetime.now(timezone.utc) - timedelta(days=settings.lookback_days)).strftime("%Y-%m-%d")
    query = f"repo:{owner}/{repo} author:{author} type:pr created:>={since_date}"
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(
            f"{BASE}/search/issues",
            headers=_headers(),
            params={"q": query, "per_page": 50, "sort": "updated", "order": "desc"},
        )
        if r.status_code != 200:
            return []
        items = r.json().get("items", [])
        # Enrich with PR body
        return [
            {
                "number": p["number"],
                "title": p["title"],
                "body": (p.get("body") or "")[:500],
                "state": p["state"],
                "created_at": p["created_at"],
                "merged": p.get("pull_request", {}).get("merged_at") is not None,
            }
            for p in items
        ]
