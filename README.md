```
███████╗██╗ ██████╗ ██╗██╗      █████╗ ██╗
██╔════╝██║██╔════╝ ██║██║     ██╔══██╗██║
███████╗██║██║  ███╗██║██║     ███████║██║
╚════██║██║██║   ██║██║██║     ██╔══██║╚═╝
███████║██║╚██████╔╝██║███████╗██║  ██║██╗
╚══════╝╚═╝ ╚═════╝ ╚═╝╚══════╝╚═╝  ╚═╝╚═╝
```

<div align="center">

**Turn invisible expertise into tangible AI agents.**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Claude](https://img.shields.io/badge/Powered%20by-Claude%20Sonnet-D97706?style=flat-square&logo=anthropic&logoColor=white)](https://anthropic.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-22C55E?style=flat-square)](LICENSE)

</div>

---

## ✦ What is Sigil?

Every engineering team has at least one person who just *gets it* — the architect who knows why the payment service was built that way, the senior whose PR comments carry the weight of ten production incidents, the developer whose commits never need a follow-up fix. That knowledge lives in their head, in their git history, in thousands of code review threads — and it evaporates when they leave, burn out, or go on vacation. **Sigil captures it.**

Point Sigil at any GitHub or Azure DevOps repository and a developer's username. It reads every commit they ever made, every diff they touched, every PR they opened or reviewed, every comment thread they participated in, and every work item they owned. Claude then performs a deep intellectual autopsy — extracting a skill tree, ownership map, engineering philosophy, and commit signature. The output is two files: `identity.md` and `soul.md` — agent configuration files you can drop into any Claude-powered system to spin up an AI that thinks, codes, and reviews exactly like that engineer. **Your best people, on demand, at scale.**

---

## ◈ How It Works

```
  ┌─────────────────────────────────────────────────────────────────┐
  │                                                                 │
  │   1. POINT          2. HARVEST          3. DISTIL              │
  │                                                                 │
  │   Give Sigil a      Sigil fetches        Claude reads          │
  │   repo URL and      commits, diffs,      everything and        │
  │   a username.       PRs, comments,       extracts a deep       │
  │                     work items, and      intellectual          │
  │   GitHub or ADO     the repo tree.       fingerprint.          │
  │   supported.                                                    │
  │                                                                 │
  │   4. GENERATE                                                   │
  │                                                                 │
  │   Two agent files land on disk:                                 │
  │   · identity.md  →  who this engineer IS                       │
  │   · soul.md      →  how they THINK and CODE                    │
  │                                                                 │
  │   Drop them into Claude Code, Team Claw, or any                │
  │   Claude-powered agent system. Done.                           │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘
```

---

## ⬡ What Sigil Extracts

Sigil synthesizes every available signal in the repository. Nothing is left unread.

| Signal Source | What Is Captured |
|---|---|
| **Commit history** | Message style, cadence, fix-vs-feature ratio, scope of change per commit, commit size discipline |
| **Code diffs** | Language distribution, abstractions introduced, refactoring patterns, test coverage behavior, file naming conventions |
| **Pull requests** | Feature ownership, PR size and description quality, how they break down problems, review readiness |
| **PR comment threads** | Authored comments reveal how they give feedback; received comments reveal blind spots, growth areas, and what reviewers flag repeatedly |
| **Work items** | Domain ownership, feature areas driven end-to-end, issue resolution patterns, tagging conventions |
| **Repository tree** | Architecture familiarity — which directories they own vs. touch occasionally, whether they work across layers or specialize |
| **Key files** | Entry points, config files, core modules — evidence of how they reason about system structure |

---

## ⟡ The Output

Every analysis produces three artifacts, all persisted to disk under `personas/`.

### `profile.json` — The full intellectual profile

```jsonc
{
  "name": "Tim Neutkens",
  "username": "timneutkens",
  "headline": "Next.js co-author who obsessively optimizes every millisecond of developer experience",
  "summary": "Tim operates at the intersection of framework architecture and developer ergonomics...",
  "superpower": "Finds and eliminates cold-path overhead others walk past every day",
  "total_commits": 80,
  "repo": "vercel/next.js",
  "skill_tree": [
    {
      "category": "Build System & Pipeline",
      "proficiency": 97,
      "skills": [
        {
          "name": "Build orchestration",
          "level": 97,
          "evidence": "Added .next/trace-build with high-level span instrumentation...",
          "commits": 8
        }
        // ...
      ]
    }
    // ...
  ],
  "feature_areas": ["App Router internals", "Turbopack integration", "Dev server startup"],
  "engineering_philosophy": "...",
  "patterns": ["small focused commits", "evidence-driven decisions", "deferred module loading"],
  "tags": ["build-systems", "performance", "typescript", "rust"],
  "identity_md": "...",   // full agent identity file
  "soul_md": "..."        // full agent soul file
}
```

### `identity.md` — Who this engineer is

The `identity.md` file establishes the agent's **persona**: their name, role, expertise domains, headline, and a structured self-introduction. This is the file that makes the agent *claim* its identity when asked "who are you?" — grounding every response in the specific developer's background and ownership history.

### `soul.md` — How they think and code

The `soul.md` file is the **behavioral kernel**: their engineering philosophy, characteristic patterns, how they approach code review, what they care about in a PR, their commit discipline, and the mental models they apply. Where `identity.md` says *who*, `soul.md` says *how*. Drop both into a system prompt and the resulting agent won't just know about the codebase — it will reason about it the way that developer would.

---

## ▶ Quick Start

Three commands to running:

```bash
# 1. Clone and install
git clone https://github.com/your-org/sigil
cd sigil/backend
pip install -r requirements.txt

# 2. Configure (see .env table below)
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY and GITHUB_TOKEN

# 3. Start the server (serves UI at http://localhost:8000)
uvicorn main:app --reload --port 8000
```

Then open `http://localhost:8000` and enter any public GitHub repo + username. The first analysis takes ~30–60 seconds depending on commit volume. Results are cached to disk — subsequent loads are instant.

**Azure DevOps** repos are supported with a PAT. Add `ADO_PAT=your_pat` to `.env` and use the full ADO URL: `https://{org}.visualstudio.com/{project}/_git/{repo}`.

---

## ⚙ Configuration

Create a `.env` file in `backend/` with the following variables:

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | **Yes** | — | Anthropic API key. Get one at [console.anthropic.com](https://console.anthropic.com) |
| `GITHUB_TOKEN` | For private repos | auto via `gh auth` | GitHub PAT with `repo` scope. Falls back to `gh auth token` automatically |
| `ADO_PAT` | For ADO repos | — | Azure DevOps Personal Access Token with Code (Read) scope |
| `ADO_TOKEN` | For ADO repos | — | Azure DevOps OAuth access token (alternative to PAT) |
| `MODEL` | No | `claude-sonnet-4-6` | Anthropic model to use for analysis |
| `MAX_COMMITS` | No | `500` | Hard cap on commits fetched per developer |
| `LOOKBACK_DAYS` | No | `365` | Rolling window of commit history to analyze (days) |
| `PERSONAS_DIR` | No | `personas` | Directory where agent files are persisted |

**Minimal `.env` for public GitHub repos:**
```env
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
```

---

## ◈ API Reference

The FastAPI backend exposes a clean REST API. Interactive docs are available at `http://localhost:8000/docs`.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/analyze` | Run analysis for a repo + username. Accepts `{ repo, username, force_refresh }`. Returns full profile JSON. Results are cached — re-analyzing is instant unless `force_refresh: true`. |
| `GET` | `/api/profiles` | List all saved profiles (lightweight: headline, superpower, tags, commit count). Sorted newest first. |
| `GET` | `/api/profiles/{cache_key}` | Fetch a full profile by its cache key. |
| `DELETE` | `/api/profiles/{cache_key}` | Delete a profile from cache and disk. |
| `GET` | `/api/export/{cache_key}/identity.md` | Download `identity.md` as a file attachment. |
| `GET` | `/api/export/{cache_key}/soul.md` | Download `soul.md` as a file attachment. |
| `GET` | `/health` | Health check. Returns model config, token status, and count of cached profiles. |

**Example analyze request:**
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo": "vercel/next.js", "username": "timneutkens"}'
```

**ADO repo:**
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo": "https://myorg.visualstudio.com/MyProject/_git/my-repo", "username": "alice@company.com"}'
```

---

## ✦ Use Cases

**Knowledge Preservation Before Attrition**
When a principal engineer announces they are leaving, teams typically schedule frantic knowledge transfer sessions that capture 10% of what that person actually knows. Run Sigil on their full commit history before their last day. Every pattern they internalized, every domain they owned, every review heuristic they applied — extracted and persisted as a deployable agent that new engineers can query for years afterward.

**Onboarding Acceleration**
New hires spend their first three months learning unwritten conventions: why the codebase is structured this way, whose judgment to trust on which subsystem, what "good" looks like here. Generate Sigil profiles for your two most senior engineers and give new hires an AI mentor that knows your actual codebase, your actual patterns, and your actual standards — not generic best practices from the internet.

**AI-Augmented Code Review**
Wire `soul.md` into a Claude Code agent scoped to PR review. When a PR touches the payment service, route it to the agent built from your payments lead's profile. The reviewer doesn't just check syntax — it catches the same architectural drift, the same missing edge cases, the same naming violations that the real engineer would flag, at zero marginal cost per review.

**Talent Intelligence and Skills Mapping**
Engineering leaders rarely have accurate visibility into what their teams actually know versus what their resumes claim. Run Sigil across your entire org. The resulting skill trees — grounded in real commit evidence, not self-reported skills — give you an honest map of capability: who owns what, where you have bus-factor risk, which engineers are quietly growing into new domains, and where you have critical knowledge concentrated in one person.

---

## ⟡ Why Sigil?

**Evidence over assertion.** Traditional skill tools ask engineers to tag themselves. Sigil reads what they actually shipped — diffs, not declarations. A proficiency score of 97 in "Build orchestration" means eight commits with traceable architectural impact, not a checkbox on a form.

**Depth over summary.** Sigil does not produce a skills keyword list. It produces a reasoning profile: the mental models, the commit discipline, the review heuristics, the engineering philosophy. The difference between knowing *what* someone does and knowing *how* they think is the difference between a biography and a simulation.

**GitHub and Azure DevOps, first class.** Most developer intelligence tools treat ADO as an afterthought. Sigil was built from the start to work with enterprise ADO organizations — PAT authentication, full PR thread extraction, work item ingestion — because that is where a significant share of institutional knowledge actually lives.

**Portable and composable.** The output is plain Markdown. `identity.md` and `soul.md` work with Claude Code, with Team Claw, with any Claude-based agent system, or with the raw Anthropic API. No vendor lock-in. No proprietary agent runtime. Your captured expertise is yours, in files you can version-control, share, and deploy anywhere.

---

## ◈ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          Browser (D3.js UI)                         │
│          Profile cards · Skill tree viz · Export buttons            │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTP
┌───────────────────────────────▼─────────────────────────────────────┐
│                      FastAPI Backend (:8000)                        │
│                                                                     │
│   /api/analyze ──► analyzer.py                                      │
│                         │                                           │
│              ┌──────────┼──────────┐                                │
│              ▼          ▼          ▼                                 │
│       github_client  ado_client  config                             │
│       (httpx)        (httpx)     (pydantic-settings)               │
│              │          │                                           │
│              └──────────┘                                           │
│                   │ raw data (commits, diffs, PRs, work items)      │
│                   ▼                                                  │
│           Anthropic Claude API                                      │
│           (claude-sonnet-4-6)                                       │
│                   │ profile JSON + identity.md + soul.md            │
│                   ▼                                                  │
│         personas/{cache_key}/                                       │
│           ├── profile.json                                          │
│           ├── identity.md                                           │
│           ├── soul.md                                               │
│           └── meta.json                                             │
│                                                                     │
│   In-memory cache (_cache dict) backed to disk on every write      │
│   No database required. Flat files. Zero infrastructure overhead.  │
└─────────────────────────────────────────────────────────────────────┘
```

Data flow for a fresh analysis:

1. `POST /api/analyze` arrives with `{ repo, username }`
2. `_parse_repo_url` detects GitHub vs ADO and routes accordingly
3. The appropriate client fetches commits (up to `MAX_COMMITS` within `LOOKBACK_DAYS`), diffs (sampled at 20 for prompt efficiency), PRs with full comment threads, work items, and the repo directory tree
4. `analyzer.py` builds a structured prompt and calls Claude with all signals
5. Claude returns a structured JSON profile including `identity_md` and `soul_md`
6. Profile is written to `personas/{cache_key}/` and added to the in-memory cache
7. Subsequent requests for the same `repo + username` are served from cache instantly

---

## ⬡ Contributing

Contributions are welcome. The codebase is intentionally small and readable — the entire backend is five files.

```bash
# Fork and clone
git clone https://github.com/your-fork/sigil
cd sigil/backend

# Install dev dependencies
pip install -r requirements.txt

# Run with auto-reload
uvicorn main:app --reload --port 8000

# The frontend is a single index.html — no build step required
open http://localhost:8000
```

**Good first contributions:**

- Add support for GitLab repositories (the `analyze` pattern is well-established — model `github_client.py`)
- Add a `--bulk` CLI mode to analyze all contributors in a repo in one pass
- Improve the D3.js skill tree visualization (currently radar-style — could be richer)
- Add a diff between two developers' profiles ("What does Alice know that Bob doesn't?")
- Persist the raw fetched data so re-analysis with a different prompt doesn't refetch

Please open an issue before starting large changes. Small PRs with clear descriptions are merged fastest.

---

## ◈ License

MIT — do whatever you want with it. If you build something useful on top of Sigil, a note in your README would be appreciated.

```
MIT License

Copyright (c) 2025 Sigil contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

<div align="center">

*The best engineers leave traces everywhere. Sigil reads them.*

</div>
