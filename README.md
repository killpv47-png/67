# GitHub Control Bot + GITHUB_AI

A Telegram bot that manages your whole GitHub account — repos, ZIP uploads, secrets, Actions — and ships with
**GITHUB_AI**, a Hermes-Agent-style agent that lives inside the project and knows it as its own home.
It runs as a long-lived job **inside GitHub Actions**, hands itself off to a fresh run before the 6-hour limit,
and carries every byte of state (encrypted) into the next run. Nothing is ever lost.

> فارسی: ربات کنترل گیت‌هاب از داخل تلگرام + ایجنت GITHUB_AI با معماری Hermes. داخل GitHub Actions اجرا می‌شود،
> قبل از سقف ۶ ساعت خودش را ری‌استارت می‌کند و تمام وضعیت (رمزنگاری‌شده) به اجرای بعدی منتقل می‌شود.
> زبان ربات بعد از /start انتخاب می‌شود (۱۰ زبان؛ انگلیسی و فارسی کامل).

---

## ✅ Features (all implemented & tested)

| Area | What you get |
|------|--------------|
| **Onboarding** | `/start` → choose language (10) → paste GitHub token → full account scan |
| **Account scan** | identity, repos (public/private), orgs, **running Actions jobs**, API budget, token scopes → access level **👑 GOD** / 🏛 ARCHITECT / 🛠 ENGINEER / 💻 DEVELOPER / 👁 OBSERVER / 👻 GHOST (fine-grained tokens are probed) |
| **Repositories** | list (paged), card, file tree, toggle private/issues/wiki, description, default branch, watch runs, delete (type-name confirmation) |
| **New repo wizard** | name, owner (user/org), description, private/public, README, .gitignore template, license, issues/wiki/projects/template flags → one `POST` |
| **Upload ZIP** | pick repo → send `.zip` → *"delete existing files?"* → if ZIP has exactly one top folder: *"upload folder or its contents?"* → branch → commit message → **one Git-Data commit** for all files (path-traversal & `__MACOSX` filtered) → detects `${{ secrets.X }}` in workflows and offers a 🔐 button for each **missing** secret |
| **Secrets & variables** | list / create / update / delete (libsodium sealed box), scan workflows for referenced-but-missing secrets, Actions variables |
| **Actions** | workflows, recent runs, run card with jobs, cancel, re-run / re-run-failed, job log tail, `workflow_dispatch` with ref, global "running now" view |
| **Notifications** | every step of every job is sent **and stored** (🔔 Notifications shows the last 15 + job step history) ; watched repos get run status pushes |
| **Control surfaces** | slash commands, persistent reply keyboard, inline (glass) buttons — all three drive the same handlers |
| **Docs button** | full architecture / AI / commands / security docs in EN + FA |
| **Self-restart** | checkpoint every 2 min → at `MAX_RUN_MINUTES` final checkpoint → `workflow_dispatch` via `GH_PAT` → exit; `concurrency` group guarantees a single poller; cron watchdog revives a dead bot |
| **Security** | tokens AES-256-GCM at rest (scrypt from `STATE_KEY`), whole DB re-encrypted before leaving the runner, token/secret messages deleted from chat, redaction at every output boundary, owner lock |

### 🤖 GITHUB_AI (Hermes architecture)

* Setup flow: **BASE_URL → API_KEY → `/models` fetched → pick one** (any OpenAI-compatible provider).
* **3-tier frozen system prompt** (Hermes `system_prompt.py`): SOUL.md identity + Hermes guidance blocks
  (memory, skills, tool-use enforcement, task completion, parallel calls, step-wise execution, secrets hygiene,
  Telegram platform hint) → **AGENTS.md** project map (every module, every secret, how to change things) →
  skills index, MEMORY/USER snapshot, session line, runtime environment.
* **Tools**: `terminal` (persistent cwd/env, timeout, protected env vars, blocked destructive commands),
  `read_file` / `write_file` / `patch` / `search_files`, `github_api` (30+ actions with the user's token),
  `web_search` / `web_extract` (**Tavily** via `TAVILY_API_KEY`), `memory`, `skills_list` / `skill_view` /
  `skill_manage`, `session_search` (FTS5 over past sessions), `todo_list` (live plan in Telegram).
* **Memory**: MEMORY + USER, char-budgeted, DB-persisted. **Skills**: `ghbot/ai/home/skills/**/SKILL.md`,
  created/patched by the agent, checkpointed with state.
* **Context compression** (Hermes `context_compressor.py`): prune old tool outputs → structured iterative summary
  with the Hermes template; emergency compaction on `context_length` errors.
* **Rate-limit resilience**: 429 / 5xx / network → wait (Retry-After aware, capped backoff) and **resume the same
  request**. The in-flight step is persisted (`ai_pending`), so even a **workflow restart** resumes the task from
  where it stopped — partial tool-call tails are repaired automatically.
* Live step notifications: 🤖 thinking → 🔧 tool call → ✅ result → final answer (Markdown → Telegram HTML).

---

## 🚀 Deploy (GitHub Actions hosting)

1. Create a **private** repo and push this project.
2. **Settings → Secrets and variables → Actions → Secrets**:

   | Secret | Required | Purpose |
   |--------|----------|---------|
   | `BOT_TOKEN` | ✅ | from @BotFather |
   | `STATE_KEY` | ✅ | ≥16-char random passphrase — encrypts all tokens + the checkpoint. **Back it up; losing it = losing state.** |
   | `GH_PAT` | recommended | classic PAT with `repo` + `workflow` for *this* repo → pushes `state/state.enc` to branch `ghbot-state` and dispatches the next run. Falls back to `GITHUB_TOKEN`. |
   | `TAVILY_API_KEY` (or `TAVILY`) | optional | enables web search for GITHUB_AI |

   **Variables** (optional): `OWNER_IDS` (comma-separated Telegram ids), `MAX_RUN_MINUTES` (default 330).
3. **Actions → GitHub Control Bot → Run workflow**. From then on it keeps itself alive.
4. Open the bot in Telegram → `/start`.

### Run locally
```bash
pip install -r requirements.txt
cp .env.example .env   # fill BOT_TOKEN + STATE_KEY, then export them
python main.py
```

### Tests (57, all green)
```bash
python -m pytest -q
```
* `tests/test_core.py`, `test_db.py` — crypto, redaction, access levels, ZIP analysis, i18n completeness, DB.
* `tests/test_ai_tools.py`, `test_ai_llm_agent.py` — every tool, memory budget, skills, LLM rate-limit resume,
  agent loop, compression, cancel, empty-response guard.
* `tests/test_telegram_flows.py` — **real aiogram Dispatcher** driven with synthetic Updates against a fake
  Telegram session + fake GitHub API: onboarding (EN/FA), repos, new-repo wizard, ZIP upload (wipe/strip-root/
  secrets offer), secrets/variables, Actions (cancel/rerun/logs/dispatch), settings/help, AI setup + chat + stop.
* `tests/test_lifecycle.py` — **full restart cycle**: checkpoint → handoff/dispatch → fresh runner restores DB,
  tokens, AI config, skills → interrupted AI task resumes; watch-loop notifications; wrong `STATE_KEY` handling.
* `tests/fake_tg_server.py` — boot `main.py` as a real process against a fake Bot API
  (`TELEGRAM_API_URL=http://127.0.0.1:8081`), SIGTERM → clean handoff + exit 0 (verified).

---

## 🧭 Commands
`/start` `/menu` `/lang` `/token` `/scan` `/repos` `/repo owner/name` `/newrepo` `/upload [owner/name]`
`/secrets [owner/name]` `/actions [owner/name]` `/ai <text>` `/ai_new` `/ai_stop` `/ai_setup`
`/notifications` `/settings` `/restart` `/help` `/cancel` — plus the reply keyboard and inline buttons.
When GITHUB_AI is configured, any plain text that isn't a command/button goes to the agent.

## 🏗 Architecture
```
main.py                    startup: restore checkpoint → open DB → build bot → lifecycle → resume AI → poll
ghbot/core/                config (env), crypto (AES-GCM), db (SQLite WAL+FTS5), notify, redact, logging
ghbot/github/              REST client (retry, rate-limit sleep, Git Data bulk commit, sealed secrets),
                           access levels, account scanner, ZIP flow
ghbot/telegram/            aiogram 3 routers: onboarding, menu, repos, newrepo, upload, secrets, actions,
                           settings, help, ai_chat; keyboards; middleware (owner lock, lang, fast ack)
ghbot/ai/                  GITHUB_AI: agent loop, llm client, prompt_builder, compressor, memory, skills,
                           tools/ (terminal, files, github_api, web, todo, session_search)
ghbot/ai/home/             SOUL.md, AGENTS.md (the agent's "house map"), skills/**/SKILL.md
ghbot/lifecycle/           checkpoint (encrypted DB+skills → host repo), handoff/dispatch, watch poller
ghbot/i18n/                en (source), fa (complete), ru ar tr es de fr zh hi (menus; EN fallback)
.github/workflows/bot.yml  workflow_dispatch + cron watchdog, concurrency singleton, 355-min timeout
```

### Data model (SQLite, `data/ghbot.db`)
`users` (lang, role, encrypted PAT, login, scopes, access level) · `kv` (AI config per user, owners, repo-id
map, todos, active session) · `notifications` · `jobs` (+ step log) · `watches` · `ai_sessions` ·
`ai_messages` (+ FTS5 mirror) · `ai_memory` · `ai_pending` (resumable in-flight AI step).

## 🔒 Security notes
* Your GitHub token and AI key are encrypted before storage; the entire DB is encrypted again before it is
  pushed to the `ghbot-state` branch. Rotating `STATE_KEY` intentionally starts fresh (old blob is kept).
* GITHUB_AI cannot read `.env`, `ghbot.db`, `state.enc`; cannot export protected env vars; catastrophic shell
  commands are blocked; destructive GitHub actions require explicit confirmation in the conversation.

## 🔜 Ideas for later
* Issue / PR management UI (API client already has `list_issues`, `create_issue`, `list_pulls`).
* Fuller translations for the 8 secondary languages (currently menus + onboarding; rest falls back to English).
* Optional webhook mode instead of long polling when self-hosted.

**Status**: ✅ feature-complete, 57 tests passing · **Stack**: Python 3.12 · aiogram 3 · aiosqlite · httpx · PyNaCl · cryptography · **Last updated**: 2026-10-05
