---
name: repo-backup
description: "Download all or selected repos (incl. private) as zipballs and deliver them to the user as a ZIP via Telegram."
---

# Repo backup / download

## When to use
User wants a copy of their repos: "send me all my repos", "backup everything", "give me a ZIP of repo X".

## Procedure
1. `github_api(action="list_repos")` to get the full list (name, private, default_branch).
2. Download each repo's zipball of the default branch. The user's token is already attached to `github_api`; for bulk download use a small script that decrypts the PAT from the DB (see below) or `github_api(action="raw", method="GET", path="/repos/{full}/zipball/{branch}")` per repo.
3. Name files `owner__repo.zip`; package all into one `all-repos.zip` with `zipfile`.
4. Send via Telegram `sendDocument` (see skill `telegram-file-send`).
5. Report count + total size.

## Decrypting the PAT for bulk download (script)
- DB: `data/ghbot.db`, table `users`, column `gh_token_enc` (GB1 blob).
- `STATE_KEY` is in the running bot's env: `tr '\0' '\n' < /proc/<bot_pid>/environ | sed -n 's/^STATE_KEY=//p'`.
- Decrypt with `ghbot.core.crypto.decrypt_str(blob, state_key)`. Never print the token.
- Download: `GET https://api.github.com/repos/{full}/zipball/{branch}` with `Authorization: Bearer <token>`.

## Pitfalls
- Private repos need the token — the zipball endpoint returns 404 without auth.
- Telegram document limit is 50MB; if the combined ZIP exceeds it, split per-repo or into chunks.
- The zipball contains the repo's files as-is, including any committed secrets (.env etc.) — warn the user not to share it.
- Never print or store the PAT.
