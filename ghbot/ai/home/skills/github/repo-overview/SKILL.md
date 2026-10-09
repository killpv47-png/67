---
name: repo-overview
description: "Analyze a repository: purpose, structure, workflows, referenced secrets, open issues/PRs, and red flags."
---

# Repo overview / analysis

## When to use
User asks "what is this repo?", "give me an overview", "analyze X", or you need to understand a repo before changing it.

## Procedure
1. `github_api(action="get_repo", repo=...)` — name, description, default branch, private, archived, stars.
2. `github_api(action="tree", repo=...)` — full file list; note the top-level layout and key dirs.
3. Read the entry points: README, `package.json`/`requirements.txt`/`pyproject.toml`/`go.mod`, `.env.example`, `docker-compose.yml`, main source files.
4. `github_api(action="list_workflows")` + read `.github/workflows/*.yml`; `detect_secrets` to find referenced secrets.
5. `github_api(action="list_issues")` and `list_pulls` for open work.
6. Report: purpose, stack, structure, workflows + secrets, open issues/PRs, anything that looks wrong (committed secrets, dead code, huge files).

## Pitfalls
- Don't dump whole files into chat — summarize. Read only what's needed.
- A repo with committed `.env` or tokens is a red flag — flag it, don't echo the value.
- For the host repo (this bot), prefer `bot-self-maintenance` skill.
