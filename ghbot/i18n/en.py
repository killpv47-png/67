STRINGS = {
    # --- onboarding
    "choose_lang": "🌐 <b>Choose your language</b>\nزبان خود را انتخاب کنید",
    "lang_set": "✅ Language set to <b>{lang}</b>.",
    "welcome": (
        "👋 <b>Welcome to GitHub Control Bot</b>\n\n"
        "I let you manage your GitHub account from Telegram — repositories, uploads, secrets, "
        "Actions — and I ship with <b>GITHUB_AI</b>, a Hermes-style agent that knows this project like its own home.\n\n"
        "🔑 To begin, send me a <b>GitHub Personal Access Token</b>.\n"
        "Create one at <a href=\"https://github.com/settings/tokens\">github.com/settings/tokens</a> "
        "(classic token with <code>repo</code>, <code>workflow</code>, <code>delete_repo</code>, <code>admin:org</code> for full power).\n\n"
        "🔒 Your token is encrypted with AES-256-GCM before it touches the database and never leaves this bot."
    ),
    "send_token": "🔑 Please paste your GitHub token now.",
    "token_invalid": "❌ That doesn't look like a GitHub token (expected <code>ghp_…</code>, <code>github_pat_…</code>, etc.). Try again.",
    "token_checking": "🔍 Validating token and scanning your account…",
    "token_bad": "❌ GitHub rejected the token: <code>{error}</code>\nSend another token.",
    "token_saved": "✅ Token saved (encrypted).",
    "not_owner": "⛔ This bot is private. Your Telegram id <code>{id}</code> is not authorized.",

    # --- scan report
    "scan_step": "⏳ Scanning: <b>{step}</b>…",
    "scan_report": (
        "📊 <b>Account Scan</b>\n\n"
        "👤 <b>{login}</b> {name}\n"
        "📦 Repos: <b>{repos}</b> (public {pub}, private {priv})\n"
        "🏢 Orgs: {orgs}\n"
        "⚙️ Running Actions jobs: <b>{running}</b>\n"
        "📈 API budget: {rate_rem}/{rate_lim}\n\n"
        "🔐 <b>Access level: {level_emoji} {level}</b>\n<i>{level_desc}</i>\n"
        "🧾 Scopes: <code>{scopes}</code>"
    ),
    "scan_running_item": "• <code>{repo}</code> — {name} <i>({status})</i>",
    "scan_errors": "⚠️ Partial scan: {errors}",
    "fine_grained": "fine-grained token (capabilities probed)",

    "access_god": "GOD — unrestricted: repos, workflows, deletion, organizations, admin. Handle with care.",
    "access_architect": "ARCHITECT — create/destroy repos, push code, run and edit workflows, manage secrets.",
    "access_engineer": "ENGINEER — push code, manage secrets, run & edit workflows. Cannot delete repos.",
    "access_developer": "DEVELOPER — push code & manage secrets, but cannot change workflow files.",
    "access_observer": "OBSERVER — read-only access.",
    "access_ghost": "GHOST — token works but has no useful permissions.",

    # --- main menu
    "menu_title": "🏠 <b>Main Menu</b> — {login} {level_emoji}\nChoose an action:",
    "btn_repos": "📦 Repositories",
    "btn_new_repo": "➕ New Repo",
    "btn_actions": "⚙️ Actions",
    "btn_secrets": "🔐 Secrets",
    "btn_upload": "📤 Upload ZIP",
    "btn_ai": "🤖 GITHUB_AI",
    "btn_scan": "📊 Rescan",
    "btn_notifs": "🔔 Notifications",
    "btn_help": "📖 Docs",
    "btn_settings": "⚙️ Settings",
    "btn_back": "⬅️ Back",
    "btn_cancel": "✖️ Cancel",
    "btn_yes": "✅ Yes",
    "btn_no": "❌ No",
    "btn_menu": "🏠 Menu",
    "btn_refresh": "🔄 Refresh",
    "btn_more": "➡️ More",
    "btn_prev": "⬅️ Prev",
    "cancelled": "✖️ Cancelled.",
    "need_token": "🔑 You need to set a GitHub token first. Send it now or use /token.",

    # --- repos
    "repos_title": "📦 <b>Your repositories</b> (page {page}/{pages})\nTap one to manage it:",
    "repos_empty": "📭 No repositories found.",
    "repo_card": (
        "📦 <b>{full}</b> {vis}\n{desc}\n\n"
        "⭐ {stars}  🍴 {forks}  🐛 {issues}  🌿 <code>{branch}</code>\n"
        "🕒 Updated {updated}\n🔗 {url}"
    ),
    "btn_repo_upload": "📤 Upload ZIP",
    "btn_repo_secrets": "🔐 Secrets",
    "btn_repo_actions": "⚙️ Actions",
    "btn_repo_files": "📁 Files",
    "btn_repo_watch": "🔔 Watch runs",
    "btn_repo_unwatch": "🔕 Unwatch",
    "btn_repo_settings": "🛠 Edit",
    "btn_repo_delete": "🗑 Delete",
    "btn_repo_ai": "🤖 Ask AI about this repo",
    "repo_files_title": "📁 <b>{full}</b> @ <code>{ref}</code> — {count} files\n<pre>{tree}</pre>",
    "repo_delete_confirm": "🗑 <b>Delete {full}?</b>\nThis is irreversible. Type the repo name <code>{name}</code> to confirm.",
    "repo_deleted": "🗑 Repository <b>{full}</b> deleted.",
    "repo_delete_mismatch": "❌ Name mismatch — deletion aborted.",
    "watch_on": "🔔 You will be notified about workflow runs in <b>{full}</b>.",
    "watch_off": "🔕 Stopped watching <b>{full}</b>.",
    "watch_event": "{icon} <b>{repo}</b> — <b>{name}</b>\nStatus: <b>{status}</b> {conclusion}\n🌿 {branch} · {event}\n🔗 {url}",

    # --- repo edit
    "repo_edit_title": "🛠 <b>Edit {full}</b>",
    "btn_toggle_private": "🔒 Toggle private/public",
    "btn_edit_desc": "📝 Description",
    "btn_toggle_issues": "🐛 Toggle issues",
    "btn_toggle_wiki": "📚 Toggle wiki",
    "btn_default_branch": "🌿 Default branch",
    "ask_description": "📝 Send the new description:",
    "ask_default_branch": "🌿 Send the new default branch name:",
    "repo_updated": "✅ Repository updated.",

    # --- new repo wizard
    "nr_name": "➕ <b>New repository</b>\n\nStep 1/7 — Send the repository <b>name</b>:",
    "nr_name_bad": "❌ Invalid name. Use letters, digits, <code>-</code>, <code>_</code>, <code>.</code> (max 100).",
    "nr_owner": "Step 2/7 — Create under which <b>owner</b>?",
    "nr_desc": "Step 3/7 — Send a <b>description</b> (or /skip):",
    "nr_vis": "Step 4/7 — <b>Visibility</b>:",
    "btn_private": "🔒 Private",
    "btn_public": "🌍 Public",
    "nr_readme": "Step 5/7 — Initialize with a <b>README</b>?",
    "nr_gitignore": "Step 6/7 — <b>.gitignore</b> template (or Skip):",
    "nr_license": "Step 7/7 — <b>License</b> (or Skip):",
    "btn_skip": "⏭ Skip",
    "nr_features": "Extra features (toggle, then Create):",
    "btn_issues_on": "🐛 Issues: ON",
    "btn_issues_off": "🐛 Issues: OFF",
    "btn_wiki_on": "📚 Wiki: ON",
    "btn_wiki_off": "📚 Wiki: OFF",
    "btn_projects_on": "📋 Projects: ON",
    "btn_projects_off": "📋 Projects: OFF",
    "btn_template_on": "🧩 Template repo: ON",
    "btn_template_off": "🧩 Template repo: OFF",
    "btn_create": "🚀 Create",
    "nr_summary": (
        "📋 <b>Summary</b>\n"
        "Name: <code>{owner}/{name}</code>\nVisibility: {vis}\nREADME: {readme}\n"
        ".gitignore: {gitignore}\nLicense: {license}\nDescription: {desc}\n"
        "Issues: {issues} · Wiki: {wiki} · Projects: {projects} · Template: {template}"
    ),
    "nr_creating": "🚀 Creating repository…",
    "nr_done": "🎉 Repository created: {url}",
    "nr_fail": "❌ Creation failed: <code>{error}</code>",

    # --- upload
    "up_pick_repo": "📤 <b>Upload ZIP</b>\nFirst choose the target repository:",
    "up_send_zip": "📤 Send me a <b>.zip</b> file for <b>{full}</b> (max 95 MB, ≤3000 files).",
    "up_not_zip": "❌ That is not a .zip file.",
    "up_downloading": "⬇️ Downloading ZIP…",
    "up_analyzing": "🔎 Analyzing archive…",
    "up_bad_zip": "❌ ZIP problem: {error}",
    "up_analysis": (
        "🔎 <b>Archive analysis</b>\n"
        "Files: <b>{count}</b> · Size: {size}\n"
        "Workflows: {workflows}\nSecrets referenced: {secrets}\n{skipped}"
    ),
    "up_skipped": "⚠️ Skipped {n} entries (unsafe/ignored paths).",
    "up_wipe_q": "🧹 Delete <b>all existing files</b> in <code>{full}</code> before uploading?",
    "btn_wipe_yes": "🧹 Yes, replace everything",
    "btn_wipe_no": "➕ No, merge on top",
    "up_root_q": (
        "📁 The ZIP contains a single folder <code>{root}/</code>.\n"
        "Upload the <b>folder itself</b> or its <b>contents</b> to the repo root?"
    ),
    "btn_root_keep": "📁 Keep folder",
    "btn_root_strip": "📂 Upload contents",
    "up_branch_q": "🌿 Target branch (current default: <code>{branch}</code>). Send a name or tap Use default.",
    "btn_use_default": "✅ Use default",
    "up_commit_q": "✍️ Commit message? Send text or tap Default.",
    "btn_default_msg": "✅ Default message",
    "up_starting": "🚀 Starting upload of {count} files to <code>{full}</code>@<code>{branch}</code>…",
    "up_progress": "📤 {msg}",
    "up_done": "🎉 Upload complete!\nCommit: <code>{sha}</code>\n🔗 {url}",
    "up_fail": "❌ Upload failed: <code>{error}</code>",
    "up_secrets_offer": (
        "🔐 The workflows reference these secrets:\n{list}\n\n"
        "Missing in repo: <b>{missing}</b>\nTap a secret to set it now."
    ),
    "up_secrets_all_present": "✅ All referenced secrets already exist in the repo.",

    # --- secrets
    "sec_pick_repo": "🔐 <b>Secrets</b>\nChoose a repository:",
    "sec_title": "🔐 <b>Secrets of {full}</b> ({n})\n{list}\n\nTap a secret to update/delete, or add a new one.",
    "sec_item": "• <code>{name}</code> — updated {updated}",
    "sec_none": "<i>no secrets yet</i>",
    "btn_sec_add": "➕ New secret",
    "btn_sec_scan": "🔎 Detect from workflows",
    "btn_sec_vars": "📋 Variables",
    "sec_ask_name": "🔐 Send the <b>secret name</b> (A-Z, 0-9, _):",
    "sec_name_bad": "❌ Invalid name. Use uppercase letters, digits and underscores; must not start with GITHUB_.",
    "sec_ask_value": "🔑 Send the <b>value</b> for <code>{name}</code>.\n<i>Your message will be deleted immediately after reading.</i>",
    "sec_saved": "✅ Secret <code>{name}</code> saved in <b>{full}</b> (encrypted with repo public key).",
    "sec_deleted": "🗑 Secret <code>{name}</code> deleted.",
    "sec_actions": "🔐 <code>{name}</code> in <b>{full}</b>",
    "btn_sec_update": "✏️ Update value",
    "btn_sec_delete": "🗑 Delete",
    "sec_detect_result": "🔎 Workflows reference: {all}\nMissing: <b>{missing}</b>",
    "sec_detect_none": "🔎 No workflow files found in this repo.",
    "vars_title": "📋 <b>Variables of {full}</b>\n{list}",
    "vars_item": "• <code>{name}</code> = <code>{value}</code>",
    "btn_var_add": "➕ New variable",
    "var_ask_name": "📋 Send the <b>variable name</b>:",
    "var_ask_value": "📋 Send the <b>value</b> for <code>{name}</code>:",
    "var_saved": "✅ Variable <code>{name}</code> saved.",

    # --- actions
    "act_pick_repo": "⚙️ <b>Actions</b>\nChoose a repository:",
    "act_title": "⚙️ <b>Actions — {full}</b>\n\n<b>Workflows:</b>\n{workflows}\n\n<b>Recent runs:</b>\n{runs}",
    "act_wf_item": "• {name} <code>{file}</code> [{state}]",
    "act_run_item": "{icon} #{num} {name} — {status} {conclusion} · {branch} · {age}",
    "act_none": "<i>none</i>",
    "btn_act_dispatch": "▶️ Run workflow",
    "btn_act_runs": "📜 Runs",
    "btn_act_running": "🏃 Running now",
    "act_pick_wf": "▶️ Which workflow to run?",
    "act_pick_ref": "🌿 Branch to run on (send name or Use default <code>{branch}</code>):",
    "act_dispatched": "▶️ Dispatched <b>{wf}</b> on <code>{ref}</code>. I'll notify you as it progresses.",
    "act_dispatch_fail": "❌ Dispatch failed: <code>{error}</code>\n<i>The workflow must have a <code>workflow_dispatch</code> trigger.</i>",
    "act_run_card": (
        "{icon} <b>Run #{num}</b> — {name}\nStatus: <b>{status}</b> {conclusion}\n"
        "🌿 {branch} · {event} · {age}\n🔗 {url}\n\n<b>Jobs:</b>\n{jobs}"
    ),
    "act_job_item": "{icon} {name} — {status} {conclusion}",
    "btn_run_cancel": "⏹ Cancel run",
    "btn_run_rerun": "🔁 Re-run",
    "btn_run_rerun_failed": "🔁 Re-run failed",
    "btn_run_logs": "📄 Last log",
    "act_cancelled": "⏹ Cancel requested for run #{num}.",
    "act_rerun": "🔁 Re-run requested for run #{num}.",
    "act_logs": "📄 <b>Log tail — {job}</b>\n<pre>{log}</pre>",
    "act_running_global": "🏃 <b>Running jobs across your account</b>\n{list}",
    "act_running_none": "😴 Nothing is running right now.",

    # --- notifications
    "notif_title": "🔔 <b>Recent notifications</b>\n{list}",
    "notif_none": "<i>no notifications yet</i>",
    "notif_item": "<code>{time}</code> {text}",
    "jobs_title": "🧾 <b>Recent jobs</b>\n{list}",
    "job_item": "{icon} <b>{title}</b> — {status} ({steps} steps)",

    # --- settings
    "settings_title": (
        "⚙️ <b>Settings</b>\n"
        "Language: {lang}\nGitHub: {login} ({level})\nAI: {ai}\nWatches: {watches}\n"
        "Runtime: {runtime}"
    ),
    "btn_change_lang": "🌐 Language",
    "btn_change_token": "🔑 Change GitHub token",
    "btn_ai_reset": "🤖 Reconfigure AI",
    "btn_export": "💾 Export state now",
    "btn_restart": "♻️ Restart bot (new run)",
    "export_done": "💾 State checkpoint pushed.",
    "export_fail": "❌ Checkpoint failed: {error}",
    "restart_confirm": "♻️ Hand off to a fresh workflow run now? Nothing will be lost — state is checkpointed first.",
    "restart_go": "♻️ Handing off… I'll message you from the new run in ~30–60s.",
    "restart_not_actions": "ℹ️ Not running inside GitHub Actions, restart is a local process restart.",

    # --- lifecycle
    "lifecycle_hello": "🟢 <b>Bot online</b> — run <code>#{run}</code> (attempt {attempt}).\nState restored: {restored}. Uptime budget: {minutes} min.",
    "lifecycle_bye": "🟠 Run budget reached. Checkpointing and starting a new run… back in ~1 min.",
    "lifecycle_resume_ai": "♻️ Resuming your interrupted GITHUB_AI task from where it stopped…",
    "lifecycle_no_pat": "⚠️ <code>GH_PAT</code> secret is missing — I cannot checkpoint state or restart myself. Set it in the host repo secrets.",

    # --- AI
    "ai_setup_base": (
        "🤖 <b>GITHUB_AI setup</b>\n\nStep 1/3 — Send the <b>BASE_URL</b> of an OpenAI-compatible API "
        "(e.g. <code>https://api.openai.com/v1</code>, <code>https://openrouter.ai/api/v1</code>):"
    ),
    "ai_setup_key": "Step 2/3 — Send the <b>API_KEY</b>.\n<i>Your message will be deleted after reading.</i>",
    "ai_fetching_models": "🔎 Fetching model list from <code>{base}</code>…",
    "ai_models_fail": "❌ Could not list models: <code>{error}</code>\nSend a model name manually, or /cancel.",
    "ai_pick_model": "Step 3/3 — Pick a <b>model</b> ({n} found, page {page}/{pages}) or send a name:",
    "ai_ready": "✅ GITHUB_AI ready.\nBase: <code>{base}</code>\nModel: <code>{model}</code>\n\nSend me anything — I know this project inside out.",
    "ai_home": (
        "🤖 <b>GITHUB_AI</b> — model <code>{model}</code>\n"
        "Session: <code>{session}</code> · {msgs} msgs · {compressions} compactions\n"
        "Memory: {mem} entries · Skills: {skills}\n\n"
        "Just type your request. Tools: terminal, files, GitHub API, web search{search}, memory, skills, todo."
    ),
    "btn_ai_new": "🆕 New session",
    "btn_ai_sessions": "🗂 Sessions",
    "btn_ai_memory": "🧠 Memory",
    "btn_ai_skills": "🧩 Skills",
    "btn_ai_model": "🔄 Change model",
    "btn_ai_stop": "⏹ Stop",
    "ai_new_session": "🆕 New session <code>{id}</code> started.",
    "ai_thinking": "🤖 Thinking…",
    "ai_tool_call": "🔧 <code>{tool}</code> {args}",
    "ai_tool_result": "↩️ {tool}: {summary}",
    "ai_rate_limited": "⏳ Model rate-limited — waiting {secs}s then resuming the same step (attempt {n}).",
    "ai_api_error": "⚠️ API error: <code>{error}</code> — retrying in {secs}s.",
    "ai_compressing": "🗜 Context is large — compressing older turns (nothing is lost; a summary replaces them).",
    "ai_done": "✅ Done ({iters} steps, {tools} tool calls).",
    "ai_stopped": "⏹ Stopped.",
    "ai_busy": "⏳ GITHUB_AI is still working on your previous request. Tap Stop to interrupt.",
    "ai_not_configured": "🤖 GITHUB_AI is not configured yet. Tap 🤖 GITHUB_AI to set BASE_URL, API_KEY and model.",
    "ai_sessions_title": "🗂 <b>Sessions</b>\n{list}",
    "ai_session_item": "{active} <code>{id}</code> {title} — {msgs} msgs",
    "ai_memory_title": "🧠 <b>Memory</b>\n<b>MEMORY</b>\n{memory}\n\n<b>USER</b>\n{user}",
    "ai_memory_empty": "<i>empty</i>",
    "ai_skills_title": "🧩 <b>Skills</b>\n{list}",
    "ai_skill_item": "• <code>{name}</code> — {desc}",
    "ai_max_iter": "⚠️ Reached the step limit ({n}). Send 'continue' to keep going.",
"ai_file_received": "📎 Got <b>{name}</b> — tell me what to do with it.",

    # --- help
    "help_text": "HELP_PLACEHOLDER",
    "btn_help_arch": "🏗 Architecture",
    "btn_help_ai": "🤖 GITHUB_AI",
    "btn_help_cmds": "⌨️ Commands",
    "btn_help_security": "🔒 Security",

    # --- generic
    "error_generic": "❌ Error: <code>{error}</code>",
    "gh_wait": "⏳ GitHub rate limit — waiting {secs}s before continuing…",
    "unknown": "🤔 I didn't understand that. Use the menu or /help.",
    "ok": "👌",
    "yes": "yes",
    "no": "no",
    "public": "🌍 public",
    "private": "🔒 private",
    "none": "none",
}
