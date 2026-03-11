from __future__ import annotations
import json
import re
import asyncio
import httpx
from anthropic import AsyncAnthropic
from fastapi import HTTPException
from config import settings
import github_client as gh
import ado_client as ado

client = AsyncAnthropic(api_key=settings.anthropic_api_key)

# ── Response helpers ─────────────────────────────────────────────────────────

def _extract_profile_json(msg) -> dict:
    """
    Parse the profile JSON from a Claude message.
    Raises HTTPException(500) with a clear message if:
    - the response was truncated (stop_reason == max_tokens)
    - the JSON is malformed
    """
    if msg.stop_reason == "max_tokens":
        raise HTTPException(
            status_code=500,
            detail=(
                "Claude's response was truncated — the profile JSON is incomplete. "
                "This usually means the commit history is very large. "
                "Try setting MAX_COMMITS to a lower value (e.g. 40) in your .env, "
                "or set LOOKBACK_DAYS to a shorter window."
            ),
        )
    raw = msg.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Claude returned malformed JSON: {e}. Raw start: {raw[:200]!r}",
        )

def _diff_budget(n_commits: int) -> int:
    """Per-commit diff char budget that keeps total prompt under ~160K tokens.

    160K tokens × 4 chars/token = 640K chars available for diffs.
    Min 600 chars (captures even tiny patches), max 6000 chars per commit.
    """
    return max(600, min(6000, 640_000 // max(n_commits, 1)))

def _trim_diff(diff: str, max_chars: int = 6000) -> str:
    if len(diff) <= max_chars:
        return diff
    return diff[:max_chars] + "\n... [truncated]"

# ── Prompt builders ─────────────────────────────────────────────────────────

def _repo_tree_section(repo_tree: dict | None) -> str:
    """Render compact repo structure + key file excerpts for the prompt."""
    if not repo_tree:
        return ""
    paths = repo_tree.get("paths", [])
    key_files = repo_tree.get("key_files", {})

    # Build directory tree — unique dirs up to depth 3
    dirs: set[str] = set()
    for p in paths:
        parts = p.split("/")
        for depth in range(1, min(4, len(parts))):
            dirs.add("/".join(parts[:depth]))
    dir_list = sorted(dirs)[:120]  # cap at 120 dirs

    tree_text = "\n".join(f"  {d}/" for d in dir_list) if dir_list else "  (tree unavailable)"

    key_files_text = ""
    for path, content in list(key_files.items())[:4]:
        key_files_text += f"\n### {path}\n```\n{content[:1200]}\n```\n"

    return f"\n## Repository Structure\n{tree_text}\n{key_files_text}"


def _build_analysis_prompt(
    username: str,
    repo_full: str,
    user_info: dict,
    commit_summaries: list[dict],
    pr_summaries: list[dict],
    work_items: list[dict] | None = None,
    repo_tree: dict | None = None,
) -> str:
    commits_text = "\n".join(
        f"[{c['date'][:10]}] {c['message'][:120]}\n  +{c['additions']} -{c['deletions']} across {c['files']} files\n  files: {', '.join(c['file_names'][:6])}"
        for c in commit_summaries
    )

    def _pr_line(p: dict) -> str:
        header = f"PR #{p['number']}: {p['title'][:100]}\n  {(p.get('body') or '')[:200]}"
        authored = p.get("authored_comments", [])
        received = p.get("received_comments", [])
        lines = [header]
        if authored:
            def _authored_entry(c):
                loc = f" [on {c['file']}]" if c.get('file') else ''
                return f"\"{c['content'][:100]}\"{loc}"
            excerpts = " | ".join(_authored_entry(c) for c in authored[:5])
            lines.append(f"  Author wrote: {excerpts}")
        if received:
            excerpts = " | ".join(
                f"\"{c['content'][:100]}\"{' [resolved]' if c.get('resolved') else ''}"
                for c in received[:3]
            )
            lines.append(f"  Feedback received: {excerpts}")
        return "\n".join(lines)

    prs_text = "\n".join(_pr_line(p) for p in pr_summaries[:10]) or "No PRs found."

    repo_tree_section = _repo_tree_section(repo_tree)

    work_items_section = ""
    if work_items:
        items_text = "\n".join(
            f"- [{wi['type']}] {wi['title']} ({wi['state']})"
            + (f" [tags: {wi['tags']}]" if wi.get("tags") else "")
            for wi in work_items
        )
        work_items_section = f"\n## Work Items / Features Owned\n{items_text}\n"

    diff_samples = "\n\n---\n".join(
        f"Commit: {c['message'][:80]}\n{_trim_diff(c.get('diff',''))}"
        for c in commit_summaries
        if c.get("diff")
    )

    return f"""You are an expert engineering talent analyst. Your job is to deeply analyse a developer's contributions to a specific GitHub repository and produce a rich, evidence-based intellectual profile.

## Developer
- GitHub: {username}
- Name: {user_info.get('name') or username}
- Bio: {user_info.get('bio') or 'N/A'}
- Company: {user_info.get('company') or 'N/A'}
- Public repos: {user_info.get('public_repos', 0)}
- Followers: {user_info.get('followers', 0)}

## Repository
{repo_full}

## Commit History ({len(commit_summaries)} commits analysed)
{commits_text}

## Pull Requests
{prs_text}
{work_items_section}{repo_tree_section}
## Code Diff Samples (first 15 commits)
{diff_samples}

---

## Code Review & Discussion Patterns
[Infer from PR comment excerpts: communication style, review depth, response to feedback]

## Analysis Instructions
- Use the repository structure to understand which features/components exist in the codebase
- Map each commit's file paths to specific features or modules to determine feature-level expertise
- For `feature_areas`: identify distinct product features or subsystems this developer owns (e.g., "Meeting Recording UI", "Auth Middleware") based on the files they repeatedly touched
- For `skill_tree`: go beyond generic tech names — name skills after the actual feature work (e.g., "Copilot Agent Sideloading" not just "React")
- Evidence in every skill must cite specific file names or commit messages from the data above

Produce a JSON object with EXACTLY this structure — no extra keys, no markdown fences:

{{
  "name": "{user_info.get('name') or username}",
  "username": "{username}",
  "avatar_url": "{user_info.get('avatar_url','')}",
  "headline": "One punchy sentence that captures this person's unique superpower in this repo (max 15 words)",
  "summary": "3-4 sentence narrative paragraph about their intellectual contribution and engineering style",
  "total_commits": {len(commit_summaries)},
  "repo": "{repo_full}",
  "skill_tree": [
    {{
      "category": "Category name (e.g. Frontend Engineering)",
      "color": "#hexcolor",
      "icon": "emoji",
      "proficiency": 0-100,
      "skills": [
        {{
          "name": "Skill name",
          "level": 0-100,
          "evidence": "1-2 sentence evidence from their commits",
          "commits": 0
        }}
      ]
    }}
  ],
  "patterns": [
    {{
      "title": "Engineering pattern title",
      "description": "Evidence-based observation",
      "icon": "emoji"
    }}
  ],
  "strengths": ["strength1", "strength2", "strength3", "strength4", "strength5"],
  "growth_areas": ["area1", "area2"],
  "commit_style": {{
    "avg_size": "small|medium|large",
    "frequency": "sporadic|regular|prolific",
    "message_quality": "terse|descriptive|excellent",
    "description": "1-2 sentence description of their commit style"
  }},
  "engineering_philosophy": "2-3 sentences capturing HOW they think and build — their underlying philosophy inferred from the code",
  "superpower": "Their single most distinctive technical ability in 10 words or less",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6"],
  "feature_areas": [
    {{
      "name": "Feature or component name (specific, e.g. 'Meeting Recording UI')",
      "description": "What they built or owned here — 1-2 sentences with file-level evidence",
      "files": ["path/to/key/file1.ts", "path/to/key/file2.ts"],
      "ownership": "contributor|owner|maintainer"
    }}
  ]
}}

Rules:
- skill_tree: 4-7 categories, each with 3-6 skills. Use ONLY categories you have real evidence for.
- proficiency: realistic. 95+ means world-class. Most will be 40-85.
- colors: use distinct, vibrant hex colors per category (dark-theme friendly)
- patterns: 4-6 patterns, must be specific observations not generic platitudes
- feature_areas: 3-8 items. Each must map to real files/directories in their commits. Be specific.
- ALL evidence must come from the actual commits/PRs/files shown above
- Return ONLY the JSON object, nothing else
"""

def _build_identity_prompt(profile: dict) -> str:
    return f"""Generate an identity.md file for an AI agent that embodies the expertise of this developer.

Developer profile:
{json.dumps(profile, indent=2)}

The identity.md should:
- Be written in first person as the agent
- Cover: who they are, what they're expert at, how they think, what they value
- Include their specific technical skills with context
- Reference their engineering philosophy
- Be inspiring and authentic — this is the agent's sense of self
- Length: 400-600 words
- Use markdown headers and bullet points

Write ONLY the markdown content, no commentary.
"""

def _build_soul_prompt(profile: dict) -> str:
    return f"""Generate a soul.md file — the deep personality and intellectual spirit of an AI agent that embodies this developer's expertise.

Developer profile:
{json.dumps(profile, indent=2)}

soul.md captures what the agent FEELS like to work with:
- Their intellectual curiosity and what excites them
- How they approach hard problems (their mental models)
- Their communication style and instincts
- What they refuse to compromise on (code quality, correctness, UX, etc.)
- Their unique lens on technology
- The questions they always ask
- What makes them different from a generic AI

This is NOT a skill list. It's the agent's character, instincts, and inner voice.
Length: 500-700 words. First person. Poetic but precise.

Write ONLY the markdown content, no commentary.
"""

# ── Main analysis pipeline ──────────────────────────────────────────────────

async def analyze(owner: str, repo: str, username: str) -> dict:
    # Fetch in parallel
    user_info, repo_info, commits, prs, repo_tree = await asyncio.gather(
        gh.get_user(username),
        gh.get_repo(owner, repo),
        gh.get_commits(owner, repo, username),   # date-windowed internally
        gh.get_prs(owner, repo, username),
        gh.get_repo_tree(owner, repo),
    )

    if not commits:
        raise ValueError(f"No commits found for {username} in {owner}/{repo}")

    # Fetch full diffs for ALL commits — budget adapts to commit count
    per_diff_chars = _diff_budget(len(commits))
    sem = asyncio.Semaphore(10)

    async def fetch_detail(commit: dict) -> dict:
        async with sem:
            sha = commit["sha"]
            try:
                detail = await gh.get_commit_detail_json(owner, repo, sha)
                files = detail.get("files", [])
                diff_text = "\n".join(
                    f.get("patch", "")[:per_diff_chars] for f in files[:10] if f.get("patch")
                )
                return {
                    "sha": sha[:7],
                    "message": commit["commit"]["message"].split("\n")[0],
                    "date": commit["commit"]["author"]["date"],
                    "additions": detail.get("stats", {}).get("additions", 0),
                    "deletions": detail.get("stats", {}).get("deletions", 0),
                    "files": len(files),
                    "file_names": [f["filename"] for f in files[:10]],
                    "diff": diff_text,
                }
            except Exception:
                return {
                    "sha": sha[:7],
                    "message": commit["commit"]["message"].split("\n")[0],
                    "date": commit["commit"]["author"]["date"],
                    "additions": 0, "deletions": 0, "files": 0,
                    "file_names": [], "diff": "",
                }

    commit_summaries = list(await asyncio.gather(*[fetch_detail(c) for c in commits]))

    pr_summaries = [
        {"number": p["number"], "title": p["title"], "body": p.get("body", "")}
        for p in prs
    ]

    repo_full = f"{owner}/{repo}"
    gh_commit_base = f"https://github.com/{owner}/{repo}/commit"

    # Claude analysis
    prompt = _build_analysis_prompt(
        username, repo_full, user_info, commit_summaries, pr_summaries,
        repo_tree=repo_tree,
    )
    msg = await client.messages.create(
        model=settings.model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    profile = _extract_profile_json(msg)

    # Generate identity.md and soul.md in parallel
    id_msg, soul_msg = await asyncio.gather(
        client.messages.create(
            model=settings.model, max_tokens=2048,
            messages=[{"role": "user", "content": _build_identity_prompt(profile)}],
        ),
        client.messages.create(
            model=settings.model, max_tokens=2048,
            messages=[{"role": "user", "content": _build_soul_prompt(profile)}],
        ),
    )

    profile["identity_md"] = id_msg.content[0].text.strip()
    profile["soul_md"] = soul_msg.content[0].text.strip()
    profile["commits_analyzed"] = [
        {
            "sha": c["sha"],
            "message": c["message"],
            "date": c["date"][:10],
            "url": f"{gh_commit_base}/{c['sha']}",
            "files": c.get("file_names", [])[:5],
        }
        for c in commit_summaries
        if c.get("sha")
    ]
    profile["cost"] = {
        "input_tokens": msg.usage.input_tokens + id_msg.usage.input_tokens + soul_msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens + id_msg.usage.output_tokens + soul_msg.usage.output_tokens,
    }

    return profile


async def analyze_ado(org: str, project: str, repo: str, username: str) -> dict:
    """ADO equivalent of analyze() — fetches commits/PRs from Azure DevOps."""

    # Fetch in parallel
    user_info, raw_commits, prs, work_items, repo_tree = await asyncio.gather(
        ado.get_user(username, org),
        ado.get_commits(org, project, repo, username),
        ado.get_prs_with_threads(org, project, repo, username),
        ado.get_work_items(org, project, username),
        ado.get_repo_tree(org, project, repo),
    )

    # Normalize to GitHub-compatible shape
    commits = ado.normalize_commits(raw_commits)

    if not commits:
        raise ValueError(f"No commits found for {username} in {org}/{project}/{repo}")

    # Fetch full diffs for ALL commits — budget adapts to commit count
    per_diff_chars = _diff_budget(len(commits))
    sem = asyncio.Semaphore(10)

    async def fetch_detail(commit: dict) -> dict:
        async with sem:
            sha = commit["sha"]
            try:
                detail_raw = await ado.get_commit_detail(org, project, repo, sha)
                detail = ado.normalize_commit_detail(detail_raw)
                files = detail.get("files", [])
                diff_text = "\n".join(
                    f.get("patch", "")[:per_diff_chars] for f in files[:10] if f.get("patch")
                )
                return {
                    "sha": sha[:7],
                    "message": commit["commit"]["message"].split("\n")[0],
                    "date": commit["commit"]["author"]["date"],
                    "additions": detail.get("stats", {}).get("additions", 0),
                    "deletions": detail.get("stats", {}).get("deletions", 0),
                    "files": len(files),
                    "file_names": [f["filename"] for f in files[:10]],
                    "diff": diff_text,
                }
            except Exception:
                return {
                    "sha": sha[:7],
                    "message": commit["commit"]["message"].split("\n")[0],
                    "date": commit["commit"]["author"]["date"],
                    "additions": 0, "deletions": 0, "files": 0,
                    "file_names": [], "diff": "",
                }

    commit_summaries = list(await asyncio.gather(*[fetch_detail(c) for c in commits]))

    pr_summaries = [
        {
            "number": p["number"],
            "title": p["title"],
            "body": p.get("body", ""),
            "authored_comments": p["threads"]["authored"][:10],
            "received_comments": p["threads"]["received"][:5],
        }
        for p in prs
    ]

    repo_full = f"{org}/{project}/{repo}"
    ado_commit_base = f"https://{org}.visualstudio.com/{project}/_git/{repo}/commit"

    # Claude analysis (same prompt, same pipeline)
    prompt = _build_analysis_prompt(
        username, repo_full, user_info, commit_summaries, pr_summaries,
        work_items=work_items, repo_tree=repo_tree,
    )
    msg = await client.messages.create(
        model=settings.model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )
    profile = _extract_profile_json(msg)

    id_msg, soul_msg = await asyncio.gather(
        client.messages.create(
            model=settings.model, max_tokens=2048,
            messages=[{"role": "user", "content": _build_identity_prompt(profile)}],
        ),
        client.messages.create(
            model=settings.model, max_tokens=2048,
            messages=[{"role": "user", "content": _build_soul_prompt(profile)}],
        ),
    )

    profile["identity_md"] = id_msg.content[0].text.strip()
    profile["soul_md"] = soul_msg.content[0].text.strip()
    profile["source"] = "ado"
    profile["commits_analyzed"] = [
        {
            "sha": c["sha"],
            "message": c["message"],
            "date": c["date"][:10],
            "url": f"{ado_commit_base}/{c['sha']}",
            "files": c.get("file_names", [])[:5],
        }
        for c in commit_summaries
        if c.get("sha")
    ]
    profile["cost"] = {
        "input_tokens": msg.usage.input_tokens + id_msg.usage.input_tokens + soul_msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens + id_msg.usage.output_tokens + soul_msg.usage.output_tokens,
    }

    return profile
