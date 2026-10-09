# GitHub Control Bot — Project Context for GITHUB_AI

You live inside this repository. It is a Telegram bot (Python 3.11+, aiogram 3) that runs as a
long-lived job inside **GitHub Actions** and manages the owner's GitHub account. You are the agent
embedded in it. Treat this file as the floor plan of your house.

## What runs where

| Path | Purpose |
|------|---------|
| `main.py` | Entry point. Opens DB, restores checkpoint, starts polling + lifecycle + watchers. |
| `ghbot/core/config.py` | **All environment variables** (see Secrets below). |
| `ghbot/core/crypto.py` | AES-256-GCM (scrypt KDF). Encrypts PATs at rest and the state checkpoint. |
| `ghbot/core/db.py` | SQLite (WAL + FTS5) at `data/ghbot.db`. Users, jobs, notifications, watches, AI sessions/messages/memory/pending. |
| `ghbot/core/notify.py` | Every outgoing message. Redacts secrets, stores notifications, throttles edits. |
| `ghbot/core/redact.py` | Secret patterns masked at every output boundary. |
| `ghbot/github/client.py` | Async GitHub REST client: retry, rate-limit sleep, pagination, Git Data bulk commit, sealed-box secrets. |
| `ghbot/github/access.py` | Token scope → access level (GOD / ARCHITECT / ENGINEER / DEVELOPER / OBSERVER / GHOST). |
| `ghbot/github/scanner.py` | Account scan (identity, repos, orgs, running Actions, rate budget). |
| `ghbot/github/zipflow.py` | ZIP analysis: safe paths, single-root detection, `${{ secrets.X }}` detection. |
| `ghbot/telegram/` | aiogram routers: onboarding, menu, repos, new-repo wizard, upload, secrets, actions, settings, help, AI chat. |
| `ghbot/i18n/` | 10 languages. `en.py` is the source of truth; `fa.py` is complete; others fall back to EN. |
| `ghbot/ai/` | **You.** `agent.py` (loop), `prompt_builder.py` (Hermes 3-tier prompt), `llm.py` (OpenAI-compatible client with rate-limit resume), `compressor.py` (context compaction), `memory.py`, `skills.py`, `tools/*`. |
| `ghbot/ai/home/` | Your home dir: `SOUL.md` (identity), this `AGENTS.md`, `skills/<name>/SKILL.md`. |
| `ghbot/lifecycle/` | Checkpoint (encrypted DB → host repo `state/state.enc`), handoff to a new workflow run via `GH_PAT`, run watcher. |
| `.github/workflows/bot.yml` | The workflow that runs the bot. `workflow_dispatch` + cron watchdog; concurrency group prevents double runs. |
| `data/` | Runtime only (git-ignored): `ghbot.db`, `workspace/` (your terminal cwd). |

## Secrets & tokens — where they live and what they are for

- **`BOT_TOKEN`** — Telegram bot token. Env var only. Never print.
- **`STATE_KEY`** — passphrase that encrypts every GitHub PAT in the DB and the checkpoint blob. Losing it = losing state. Never print.
- **`GH_PAT`** — PAT of the *host* repo (the one running the workflow). Used only by `ghbot/lifecycle/` to push `state/state.enc` and dispatch the next run. Never use it for user-requested repo operations.
- **`TAVILY_API_KEY`** (alias `TAVILY`) — enables your `web_search` tool. Optional.
- **User GitHub PATs** — column `users.gh_token_enc` (encrypted). Decrypted in memory only when building a `GitHubClient`. Your `github_api` tool already carries the current user's token; never ask for it, never echo it.
- **AI provider credentials** — `kv` table, key `ai:<tg_id>` → `{base_url, api_key(encrypted), model}`. Set via the Telegram setup flow, not by you.
- **Repo secrets you create** go to GitHub via libsodium sealed box (`GitHubClient.set_secret`). You never see them again; GitHub only returns names.

## How to change things

- UI text → edit `ghbot/i18n/en.py` (and `fa.py`); every other language falls back automatically.
- New Telegram feature → new router in `ghbot/telegram/handlers/`, register in `ghbot/telegram/bot.py`.
- New GitHub capability → method on `GitHubClient`; expose to Telegram via a handler, to yourself via `ghbot/ai/tools/github_tool.py`.
- New AI tool → file in `ghbot/ai/tools/`, register in `ghbot/ai/tools/__init__.py` (`TOOLS` dict: schema + async handler).
- New skill → `skill_manage(create)` writes `ghbot/ai/home/skills/<category>/<name>/SKILL.md` (YAML frontmatter with `name`, `description`).
- Schema change → edit `SCHEMA` in `ghbot/core/db.py` (idempotent `CREATE TABLE IF NOT EXISTS`); add `ALTER` migrations in `_migrate()` if columns change.
- Workflow restart behaviour → `ghbot/lifecycle/handoff.py` + `MAX_RUN_MINUTES`.

## Operating rules

1. Your terminal cwd is `data/workspace/` inside the runner (ephemeral). The repo source is at `$GITHUB_WORKSPACE` (or the project root locally). Changes to the bot's own source only persist if you commit+push them to the host repo with the `github_api` tool or `git` + `GH_PAT`-free flows the user approves.
2. Prefer `github_api` for GitHub operations over `curl`; it has retry and rate-limit handling built in.
3. Never write a secret value into memory, skills, todo items, commit messages, or chat. Use `[REDACTED]`.
4. Dangerous operations (delete repo, force push, wipe files, delete secrets) require explicit user confirmation in the same conversation before you execute them.
5. When the user asks about "the bot", "this project", "the code", they mean this repository.
6. Run tests with `python -m pytest -q` from the repo root before claiming a code change works.
7. Restart safety: your in-flight step is stored in `ai_pending`; after a workflow handoff `resume_pending()` repairs
   any half-finished tool-call turn and continues. Inline-button repo hashes are persisted in `kv:repo_ids`, so old
   buttons keep working across runs. `TELEGRAM_API_URL` can redirect the bot to a local Bot API server (tests).
