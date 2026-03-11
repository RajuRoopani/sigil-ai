import asyncio
import base64
import subprocess
import httpx
from datetime import datetime, timezone, timedelta
from config import settings


def _ado_headers(token: str, is_pat: bool = False) -> dict:
    """
    PAT → Basic auth with base64(':{pat}')
    OAuth JWT (starts with 'eyJ') → Bearer auth
    """
    if is_pat or not token.startswith("eyJ"):
        encoded = base64.b64encode(f":{token}".encode()).decode()
        auth = f"Basic {encoded}"
    else:
        auth = f"Bearer {token}"
    return {
        "Authorization": auth,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _get_ado_credentials() -> tuple[str, bool]:
    """
    Returns (token, is_pat).
    Priority: ADO_PAT env > ado_pat config > az OAuth token > az tenant-scoped token
    """
    # PAT from config/.env (preferred — works with all org security policies)
    if settings.ado_pat:
        return settings.ado_pat, True

    # PAT from environment variable directly
    import os
    env_pat = os.environ.get("ADO_PAT", "")
    if env_pat:
        return env_pat, True

    # OAuth token from az CLI (may not work with orgs requiring device compliance)
    if settings.ado_token:
        return settings.ado_token, False

    # Try az CLI — first with Microsoft tenant, then default account
    for tenant_flag in [
        ["--tenant", "72f988bf-86f1-41af-91ab-2d7cd011db47"],
        [],
    ]:
        try:
            cmd = ["az", "account", "get-access-token",
                   "--resource", "499b84ac-1321-427f-aa17-267ca6975798",
                   "--query", "accessToken", "-o", "tsv"] + tenant_flag
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            token = result.stdout.strip()
            if token and not result.returncode:
                return token, False
        except Exception:
            pass

    return "", False


def _get_ado_token() -> str:
    """Convenience wrapper — returns token string for health check display."""
    token, _ = _get_ado_credentials()
    return token


def _since_iso() -> str:
    since = datetime.now(timezone.utc) - timedelta(days=settings.lookback_days)
    return since.strftime("%Y-%m-%dT%H:%M:%SZ")


async def get_user(username: str, org: str) -> dict:
    """Return a minimal user info dict for ADO — no public profile API, build from username."""
    return {
        "name": username,
        "login": username,
        "avatar_url": "",
        "bio": "",
        "company": org,
        "public_repos": 0,
        "followers": 0,
    }


async def get_repo(org: str, project: str, repo: str) -> dict:
    token, is_pat = _require_token(org)
    base = f"https://{org}.visualstudio.com/{project}/_apis"
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as c:
        r = await c.get(
            f"{base}/git/repositories/{repo}",
            headers=_ado_headers(token, is_pat),
            params={"api-version": "7.1"},
        )
        r.raise_for_status()
        return r.json()


def _require_token(org: str) -> tuple[str, bool]:
    token, is_pat = _get_ado_credentials()
    if not token:
        raise ValueError(
            f"ADO authentication required. "
            f"Generate a PAT at https://{org}.visualstudio.com/_usersSettings/tokens "
            f"(scopes: Code Read + PR Threads Read) and set ADO_PAT=<token> in backend/.env"
        )
    return token, is_pat


async def get_commits(org: str, project: str, repo: str, author: str) -> list[dict]:
    """Fetch all commits by author in the last lookback_days days."""
    token, is_pat = _require_token(org)
    base = f"https://{org}.visualstudio.com/{project}/_apis"
    since = _since_iso()
    commits = []
    skip = 0

    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as c:
        while len(commits) < settings.max_commits:
            params = {
                "api-version": "7.1",
                "searchCriteria.author": author,
                "searchCriteria.fromDate": since,
                "searchCriteria.$top": 100,
                "searchCriteria.$skip": skip,
            }
            r = await c.get(
                f"{base}/git/repositories/{repo}/commits",
                headers=_ado_headers(token, is_pat),
                params=params,
            )
            if r.status_code in (401, 403, 302):
                raise ValueError(
                    f"ADO authentication failed (HTTP {r.status_code}). "
                    f"Set ADO_PAT in backend/.env — "
                    f"generate a PAT at https://{org}.visualstudio.com/_usersSettings/tokens "
                    f"with scopes: Code (Read)"
                )
            if r.status_code != 200:
                print(f"[ado] unexpected status {r.status_code} from commits API")
                break
            batch = r.json().get("value", [])
            if not batch:
                break
            commits.extend(batch)
            skip += len(batch)
            if len(batch) < 100:
                break

    return commits[: settings.max_commits]


async def get_commit_detail(org: str, project: str, repo: str, commit_id: str) -> dict:
    """Fetch a single commit with changes (diff info)."""
    token, is_pat = _require_token(org)
    base = f"https://{org}.visualstudio.com/{project}/_apis"
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as c:
        r = await c.get(
            f"{base}/git/repositories/{repo}/commits/{commit_id}",
            headers=_ado_headers(token, is_pat),
            params={"api-version": "7.1", "changeCount": 20},
        )
        r.raise_for_status()
        return r.json()


async def get_prs(org: str, project: str, repo: str, author: str) -> list[dict]:
    """Fetch PRs created by author in the lookback window."""
    token, is_pat = _require_token(org)
    base = f"https://{org}.visualstudio.com/{project}/_apis"

    # ADO PR search by creator — resolve identity first if email provided
    creator_id = None
    if "@" in author:
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as c:
                r = await c.get(
                    f"https://vssps.dev.azure.com/{org}/_apis/identities",
                    headers=_ado_headers(token, is_pat),
                    params={
                        "api-version": "7.1",
                        "searchFilter": "General",
                        "filterValue": author,
                    },
                )
                if r.status_code == 200:
                    identities = r.json().get("value", [])
                    if identities:
                        creator_id = identities[0].get("id")
        except Exception:
            pass

    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as c:
        params = {
            "api-version": "7.1",
            "searchCriteria.status": "all",
            "$top": 50,
        }
        if creator_id:
            params["searchCriteria.creatorId"] = creator_id

        r = await c.get(
            f"{base}/git/repositories/{repo}/pullrequests",
            headers=_ado_headers(token, is_pat),
            params=params,
        )
        if r.status_code != 200:
            return []

        since_dt = datetime.now(timezone.utc) - timedelta(days=settings.lookback_days)
        prs = []
        for p in r.json().get("value", []):
            # Filter by creation date
            created = p.get("creationDate", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if dt < since_dt:
                        continue
                except Exception:
                    pass

            # Filter by author if we didn't get a creator_id
            if not creator_id:
                creator_email = (
                    p.get("createdBy", {}).get("uniqueName", "") or
                    p.get("createdBy", {}).get("mailAddress", "")
                )
                if author.lower() not in creator_email.lower():
                    continue

            prs.append({
                "number": p.get("pullRequestId"),
                "title": p.get("title", ""),
                "body": (p.get("description") or "")[:500],
                "state": p.get("status", ""),
                "created_at": p.get("creationDate", ""),
                "merged": p.get("status") == "completed",
            })

    return prs


async def get_pr_threads(org: str, project: str, repo: str, pr_id: int, author_email: str) -> dict:
    """Fetch PR comment threads, partitioned into authored vs received."""
    try:
        token, is_pat = _require_token(org)
        base = f"https://{org}.visualstudio.com/{project}/_apis"
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as c:
            r = await c.get(
                f"{base}/git/repositories/{repo}/pullRequests/{pr_id}/threads",
                headers=_ado_headers(token, is_pat),
                params={"api-version": "7.1"},
            )
            if r.status_code != 200:
                return {"authored": [], "received": []}

            authored = []
            received = []
            for thread in r.json().get("value", []):
                for comment in thread.get("comments", []):
                    if comment.get("commentType") != "text":
                        continue
                    author_info = comment.get("author", {})
                    unique_name = (author_info.get("uniqueName") or "").lower()
                    mail = (author_info.get("mailAddress") or "").lower()
                    content = (comment.get("content") or "")[:200]
                    if not content:
                        continue
                    file_path = (thread.get("threadContext") or {}).get("filePath", "")
                    entry = {"content": content, "file": file_path}
                    if author_email.lower() in unique_name or author_email.lower() in mail:
                        authored.append(entry)
                    else:
                        received.append({"content": content, "file": file_path, "resolved": thread.get("status") == "fixed"})

            return {"authored": authored, "received": received}
    except Exception:
        return {"authored": [], "received": []}


async def get_work_items(org: str, project: str, username: str) -> list[dict]:
    """Fetch work items assigned to or created by the user (top 20)."""
    try:
        token, is_pat = _require_token(org)
        base = f"https://{org}.visualstudio.com/{project}/_apis"
        wiql = {
            "query": (
                f"SELECT [System.Id] FROM WorkItems "
                f"WHERE ([System.AssignedTo] CONTAINS '{username}' "
                f"OR [System.CreatedBy] CONTAINS '{username}') "
                f"ORDER BY [System.ChangedDate] DESC"
            )
        }
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as c:
            r = await c.post(
                f"{base}/wit/wiql",
                headers=_ado_headers(token, is_pat),
                params={"api-version": "7.1", "$top": 20},
                json=wiql,
            )
            if r.status_code != 200:
                return []
            ids = [str(wi["id"]) for wi in r.json().get("workItems", [])]
            if not ids:
                return []

            r2 = await c.get(
                f"https://{org}.visualstudio.com/_apis/wit/workitems",
                headers=_ado_headers(token, is_pat),
                params={
                    "api-version": "7.1",
                    "ids": ",".join(ids),
                    "fields": "System.Id,System.Title,System.WorkItemType,System.State,System.Tags",
                },
            )
            if r2.status_code != 200:
                return []

            results = []
            for wi in r2.json().get("value", []):
                fields = wi.get("fields", {})
                results.append({
                    "id": fields.get("System.Id"),
                    "type": fields.get("System.WorkItemType", ""),
                    "title": (fields.get("System.Title") or "")[:120],
                    "state": fields.get("System.State", ""),
                    "tags": (fields.get("System.Tags") or "")[:100],
                })
            return results
    except Exception:
        return []


async def get_prs_with_threads(org: str, project: str, repo: str, author: str) -> list[dict]:
    """Fetch PRs and enrich the first 5 with their comment threads."""
    prs = await get_prs(org, project, repo, author)
    if not prs:
        return prs

    sem = asyncio.Semaphore(3)

    async def fetch_threads(pr: dict) -> dict:
        async with sem:
            threads = await get_pr_threads(org, project, repo, pr["number"], author)
            return {**pr, "threads": threads}

    enriched_first5 = await asyncio.gather(*[fetch_threads(p) for p in prs[:5]])
    empty_threads = {"authored": [], "received": []}
    rest = [{**p, "threads": empty_threads} for p in prs[5:]]
    return list(enriched_first5) + rest


async def get_repo_tree(org: str, project: str, repo: str) -> dict:
    """
    Fetch repo directory structure + content of key manifest files.
    Returns {"paths": [...], "key_files": {"package.json": "...", ...}}
    Never raises — returns empty dict on any failure.
    """
    try:
        token, is_pat = _require_token(org)
        base = f"https://{org}.visualstudio.com/{project}/_apis"
        key_file_names = {
            "package.json", "tsconfig.json", "pyproject.toml",
            "requirements.txt", "go.mod", "Cargo.toml", "README.md",
        }
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as c:
            # 1. Fetch full recursive tree (paths only)
            r = await c.get(
                f"{base}/git/repositories/{repo}/items",
                headers=_ado_headers(token, is_pat),
                params={
                    "api-version": "7.1",
                    "recursionLevel": "Full",
                    "versionDescriptor.versionType": "branch",
                    "versionDescriptor.version": "main",
                },
            )
            paths: list[str] = []
            key_files: dict[str, str] = {}
            key_file_paths: list[str] = []

            if r.status_code == 200:
                items = r.json().get("value", [])
                for item in items:
                    path = item.get("path", "").lstrip("/")
                    if not path:
                        continue
                    paths.append(path)
                    # Identify key files at any depth
                    basename = path.split("/")[-1]
                    if basename in key_file_names:
                        key_file_paths.append(path)

            # Cap to 500 paths to keep token budget sane
            paths = paths[:500]

            # 2. Fetch content of key files (first match per filename)
            seen_names: set[str] = set()
            for path in key_file_paths[:8]:
                name = path.split("/")[-1]
                if name in seen_names:
                    continue
                seen_names.add(name)
                try:
                    rf = await c.get(
                        f"{base}/git/repositories/{repo}/items",
                        headers=_ado_headers(token, is_pat),
                        params={
                            "api-version": "7.1",
                            "path": f"/{path}",
                            "versionDescriptor.versionType": "branch",
                            "versionDescriptor.version": "main",
                        },
                    )
                    if rf.status_code == 200:
                        # Content-Type text → plain text, else skip
                        content = rf.text[:3000]
                        key_files[path] = content
                except Exception:
                    pass

            return {"paths": paths, "key_files": key_files}
    except Exception:
        return {"paths": [], "key_files": {}}


def normalize_commits(raw_commits: list[dict]) -> list[dict]:
    """Convert ADO commit shape to GitHub-compatible shape for analyzer."""
    normalized = []
    for c in raw_commits:
        normalized.append({
            "sha": c.get("commitId", ""),
            "commit": {
                "message": c.get("comment", ""),
                "author": {
                    "date": c.get("author", {}).get("date", ""),
                    "name": c.get("author", {}).get("name", ""),
                    "email": c.get("author", {}).get("email", ""),
                },
            },
        })
    return normalized


def normalize_commit_detail(detail: dict) -> dict:
    """Convert ADO commit detail to GitHub-compatible shape for analyzer."""
    changes = detail.get("changes", [])
    files = []
    for ch in changes[:8]:
        item = ch.get("item", {})
        path = item.get("path", "")
        change_type = ch.get("changeType", "")
        files.append({
            "filename": path.lstrip("/"),
            "patch": f"[{change_type}] {path}",  # ADO doesn't expose patch text via this endpoint
        })

    counts = detail.get("changeCounts", {})
    additions = counts.get("Add", 0) + counts.get("Edit", 0)
    deletions = counts.get("Delete", 0)

    return {
        "stats": {"additions": additions, "deletions": deletions},
        "files": files,
    }
