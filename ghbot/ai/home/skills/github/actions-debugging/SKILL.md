---
name: actions-debugging
description: "Diagnose a failing GitHub Actions run: fetch jobs, read the failing step's log tail, propose and apply a fix."
---

# Actions debugging

1. `github_api(action="list_runs", repo=..., status="failure")` → pick the run.
2. `github_api(action="run_jobs", repo=..., run_id=...)` → find jobs with `conclusion=failure`.
3. `github_api(action="job_log", repo=..., job_id=...)` → read the tail. Look for the first `##[error]` line.
4. Common causes: missing secret (`secrets.X` empty), wrong `runs-on`, missing `workflow_dispatch`, `permissions:` too narrow, pip/npm version pin.
5. Fix the workflow file with `github_api(action="put_file")` for a single-file fix (read it first with `get_file`).
6. `github_api(action="rerun", repo=..., run_id=..., failed_only=true)` and tell the user the bot will notify if the repo is watched.

Never paste full logs into chat — summarize the error and quote ≤15 relevant lines.
