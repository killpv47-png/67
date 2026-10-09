---
name: secrets-management
description: "Create/update/delete Actions secrets and variables; detect which secrets a repo's workflows need."
---

# Secrets management

- List: `github_api(action="list_secrets", repo=...)` (names + updated_at only).
- Detect needed: `github_api(action="detect_secrets", repo=...)` scans `.github/workflows/` for `${{ secrets.X }}`.
- Set: `github_api(action="set_secret", repo=..., name=..., value=...)` — value is sealed with the repo public key (libsodium). **Only call this with a value the user gave you in this conversation; never invent or reuse values from memory.**
- Variables (non-secret): `set_variable` / `list_variables`.
- Names: `[A-Z0-9_]+`, must not start with `GITHUB_`.
- Special secrets in this project: `GH_PAT` (host repo PAT for self-restart), `BOT_TOKEN`, `STATE_KEY`, `TAVILY_API_KEY`.
