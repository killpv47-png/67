STRINGS = {
    "choose_lang": "🌐 <b>Choose your language</b>\nزبان خود را انتخاب کنید",
    "lang_set": "✅ زبان روی <b>{lang}</b> تنظیم شد.",
    "welcome": (
        "👋 <b>به ربات کنترل گیت‌هاب خوش آمدید</b>\n\n"
        "با من می‌توانید اکانت گیت‌هاب‌تان را از داخل تلگرام مدیریت کنید — ریپوها، آپلود فایل، سکرت‌ها، "
        "Actions — و <b>GITHUB_AI</b> را هم دارم؛ یک ایجنت با معماری Hermes که این پروژه را مثل خانهٔ خودش می‌شناسد.\n\n"
        "🔑 برای شروع، <b>توکن شخصی گیت‌هاب</b> (PAT) خود را بفرستید.\n"
        "از <a href=\"https://github.com/settings/tokens\">github.com/settings/tokens</a> بسازید "
        "(توکن کلاسیک با <code>repo</code>، <code>workflow</code>، <code>delete_repo</code>، <code>admin:org</code> برای دسترسی کامل).\n\n"
        "🔒 توکن شما قبل از ذخیره با AES-256-GCM رمزنگاری می‌شود و هرگز از این ربات خارج نمی‌شود."
    ),
    "send_token": "🔑 لطفاً توکن گیت‌هاب خود را همین حالا بفرستید.",
    "token_invalid": "❌ این شبیه توکن گیت‌هاب نیست (انتظار <code>ghp_…</code> یا <code>github_pat_…</code> می‌رود). دوباره تلاش کنید.",
    "token_checking": "🔍 در حال اعتبارسنجی توکن و اسکن اکانت…",
    "token_bad": "❌ گیت‌هاب توکن را رد کرد: <code>{error}</code>\nتوکن دیگری بفرستید.",
    "token_saved": "✅ توکن (رمزنگاری‌شده) ذخیره شد.",
    "not_owner": "⛔ این ربات خصوصی است. شناسهٔ تلگرام شما <code>{id}</code> مجاز نیست.",

    "scan_step": "⏳ در حال اسکن: <b>{step}</b>…",
    "scan_report": (
        "📊 <b>اسکن اکانت</b>\n\n"
        "👤 <b>{login}</b> {name}\n"
        "📦 ریپوها: <b>{repos}</b> (عمومی {pub}، خصوصی {priv})\n"
        "🏢 سازمان‌ها: {orgs}\n"
        "⚙️ جاب‌های در حال اجرای Actions: <b>{running}</b>\n"
        "📈 بودجهٔ API: {rate_rem}/{rate_lim}\n\n"
        "🔐 <b>سطح دسترسی: {level_emoji} {level}</b>\n<i>{level_desc}</i>\n"
        "🧾 اسکوپ‌ها: <code>{scopes}</code>"
    ),
    "scan_running_item": "• <code>{repo}</code> — {name} <i>({status})</i>",
    "scan_errors": "⚠️ اسکن ناقص: {errors}",
    "fine_grained": "توکن fine-grained (قابلیت‌ها با تست تشخیص داده شد)",

    "access_god": "GOD — بدون محدودیت: ریپوها، ورک‌فلوها، حذف، سازمان‌ها، ادمین. با احتیاط استفاده کنید.",
    "access_architect": "ARCHITECT — ساخت/حذف ریپو، پوش کد، اجرا و ویرایش ورک‌فلو، مدیریت سکرت‌ها.",
    "access_engineer": "ENGINEER — پوش کد، مدیریت سکرت‌ها، اجرا و ویرایش ورک‌فلوها. حذف ریپو ندارد.",
    "access_developer": "DEVELOPER — پوش کد و مدیریت سکرت‌ها، اما نمی‌تواند فایل‌های ورک‌فلو را تغییر دهد.",
    "access_observer": "OBSERVER — فقط خواندن.",
    "access_ghost": "GHOST — توکن معتبر است اما دسترسی مفیدی ندارد.",

    "menu_title": "🏠 <b>منوی اصلی</b> — {login} {level_emoji}\nیک عملیات انتخاب کنید:",
    "btn_repos": "📦 ریپوها",
    "btn_new_repo": "➕ ریپوی جدید",
    "btn_actions": "⚙️ Actions",
    "btn_secrets": "🔐 سکرت‌ها",
    "btn_upload": "📤 آپلود ZIP",
    "btn_ai": "🤖 GITHUB_AI",
    "btn_scan": "📊 اسکن مجدد",
    "btn_notifs": "🔔 اعلان‌ها",
    "btn_help": "📖 توضیحات",
    "btn_settings": "⚙️ تنظیمات",
    "btn_back": "⬅️ بازگشت",
    "btn_cancel": "✖️ لغو",
    "btn_yes": "✅ بله",
    "btn_no": "❌ خیر",
    "btn_menu": "🏠 منو",
    "btn_refresh": "🔄 تازه‌سازی",
    "btn_more": "➡️ بعدی",
    "btn_prev": "⬅️ قبلی",
    "cancelled": "✖️ لغو شد.",
    "need_token": "🔑 اول باید توکن گیت‌هاب تنظیم کنید. همین حالا بفرستید یا از /token استفاده کنید.",

    "repos_title": "📦 <b>ریپوهای شما</b> (صفحهٔ {page}/{pages})\nروی یکی بزنید تا مدیریتش کنید:",
    "repos_empty": "📭 ریپویی پیدا نشد.",
    "repo_card": (
        "📦 <b>{full}</b> {vis}\n{desc}\n\n"
        "⭐ {stars}  🍴 {forks}  🐛 {issues}  🌿 <code>{branch}</code>\n"
        "🕒 آخرین تغییر {updated}\n🔗 {url}"
    ),
    "btn_repo_upload": "📤 آپلود ZIP",
    "btn_repo_secrets": "🔐 سکرت‌ها",
    "btn_repo_actions": "⚙️ Actions",
    "btn_repo_files": "📁 فایل‌ها",
    "btn_repo_watch": "🔔 دنبال‌کردن اجراها",
    "btn_repo_unwatch": "🔕 توقف دنبال‌کردن",
    "btn_repo_settings": "🛠 ویرایش",
    "btn_repo_delete": "🗑 حذف",
    "btn_repo_ai": "🤖 دربارهٔ این ریپو از AI بپرس",
    "repo_files_title": "📁 <b>{full}</b> @ <code>{ref}</code> — {count} فایل\n<pre>{tree}</pre>",
    "repo_delete_confirm": "🗑 <b>حذف {full}؟</b>\nاین کار برگشت‌ناپذیر است. برای تأیید نام ریپو <code>{name}</code> را تایپ کنید.",
    "repo_deleted": "🗑 ریپوی <b>{full}</b> حذف شد.",
    "repo_delete_mismatch": "❌ نام مطابقت نداشت — حذف لغو شد.",
    "watch_on": "🔔 از این پس دربارهٔ اجراهای ورک‌فلو در <b>{full}</b> به شما اطلاع می‌دهم.",
    "watch_off": "🔕 دنبال‌کردن <b>{full}</b> متوقف شد.",
    "watch_event": "{icon} <b>{repo}</b> — <b>{name}</b>\nوضعیت: <b>{status}</b> {conclusion}\n🌿 {branch} · {event}\n🔗 {url}",

    "repo_edit_title": "🛠 <b>ویرایش {full}</b>",
    "btn_toggle_private": "🔒 تغییر خصوصی/عمومی",
    "btn_edit_desc": "📝 توضیحات",
    "btn_toggle_issues": "🐛 روشن/خاموش Issues",
    "btn_toggle_wiki": "📚 روشن/خاموش Wiki",
    "btn_default_branch": "🌿 برنچ پیش‌فرض",
    "ask_description": "📝 توضیحات جدید را بفرستید:",
    "ask_default_branch": "🌿 نام برنچ پیش‌فرض جدید را بفرستید:",
    "repo_updated": "✅ ریپو به‌روزرسانی شد.",

    "nr_name": "➕ <b>ریپوی جدید</b>\n\nمرحلهٔ ۱/۷ — <b>نام</b> ریپو را بفرستید:",
    "nr_name_bad": "❌ نام نامعتبر است. از حروف، ارقام، <code>-</code>، <code>_</code>، <code>.</code> استفاده کنید (حداکثر ۱۰۰).",
    "nr_owner": "مرحلهٔ ۲/۷ — زیر کدام <b>مالک</b> ساخته شود؟",
    "nr_desc": "مرحلهٔ ۳/۷ — یک <b>توضیح</b> بفرستید (یا /skip):",
    "nr_vis": "مرحلهٔ ۴/۷ — <b>وضعیت نمایش</b>:",
    "btn_private": "🔒 خصوصی",
    "btn_public": "🌍 عمومی",
    "nr_readme": "مرحلهٔ ۵/۷ — با <b>README</b> ساخته شود؟",
    "nr_gitignore": "مرحلهٔ ۶/۷ — قالب <b>.gitignore</b> (یا رد شدن):",
    "nr_license": "مرحلهٔ ۷/۷ — <b>لایسنس</b> (یا رد شدن):",
    "btn_skip": "⏭ رد شدن",
    "nr_features": "امکانات اضافه (تغییر دهید، سپس ساخت):",
    "btn_issues_on": "🐛 Issues: روشن",
    "btn_issues_off": "🐛 Issues: خاموش",
    "btn_wiki_on": "📚 Wiki: روشن",
    "btn_wiki_off": "📚 Wiki: خاموش",
    "btn_projects_on": "📋 Projects: روشن",
    "btn_projects_off": "📋 Projects: خاموش",
    "btn_template_on": "🧩 ریپوی قالب: روشن",
    "btn_template_off": "🧩 ریپوی قالب: خاموش",
    "btn_create": "🚀 ساخت",
    "nr_summary": (
        "📋 <b>خلاصه</b>\n"
        "نام: <code>{owner}/{name}</code>\nنمایش: {vis}\nREADME: {readme}\n"
        ".gitignore: {gitignore}\nلایسنس: {license}\nتوضیح: {desc}\n"
        "Issues: {issues} · Wiki: {wiki} · Projects: {projects} · قالب: {template}"
    ),
    "nr_creating": "🚀 در حال ساخت ریپو…",
    "nr_done": "🎉 ریپو ساخته شد: {url}",
    "nr_fail": "❌ ساخت ناموفق: <code>{error}</code>",

    "up_pick_repo": "📤 <b>آپلود ZIP</b>\nاول ریپوی مقصد را انتخاب کنید:",
    "up_send_zip": "📤 یک فایل <b>.zip</b> برای <b>{full}</b> بفرستید (حداکثر ۹۵ مگابایت، ≤۳۰۰۰ فایل).",
    "up_not_zip": "❌ این فایل .zip نیست.",
    "up_downloading": "⬇️ در حال دانلود ZIP…",
    "up_analyzing": "🔎 در حال تحلیل آرشیو…",
    "up_bad_zip": "❌ مشکل ZIP: {error}",
    "up_analysis": (
        "🔎 <b>تحلیل آرشیو</b>\n"
        "فایل‌ها: <b>{count}</b> · حجم: {size}\n"
        "ورک‌فلوها: {workflows}\nسکرت‌های ارجاع‌شده: {secrets}\n{skipped}"
    ),
    "up_skipped": "⚠️ {n} مورد نادیده گرفته شد (مسیر ناامن/غیرضروری).",
    "up_wipe_q": "🧹 <b>همهٔ فایل‌های موجود</b> در <code>{full}</code> قبل از آپلود حذف شوند؟",
    "btn_wipe_yes": "🧹 بله، همه جایگزین شود",
    "btn_wipe_no": "➕ نه، روی فایل‌های قبلی اضافه شود",
    "up_root_q": (
        "📁 این ZIP فقط یک پوشه به نام <code>{root}/</code> دارد.\n"
        "<b>خود پوشه</b> آپلود شود یا <b>محتویات داخل آن</b> در ریشهٔ ریپو؟"
    ),
    "btn_root_keep": "📁 خود پوشه",
    "btn_root_strip": "📂 محتویات پوشه",
    "up_branch_q": "🌿 برنچ مقصد (پیش‌فرض فعلی: <code>{branch}</code>). یک نام بفرستید یا «پیش‌فرض» را بزنید.",
    "btn_use_default": "✅ پیش‌فرض",
    "up_commit_q": "✍️ پیام کامیت؟ متن بفرستید یا «پیش‌فرض» را بزنید.",
    "btn_default_msg": "✅ پیام پیش‌فرض",
    "up_starting": "🚀 شروع آپلود {count} فایل به <code>{full}</code>@<code>{branch}</code>…",
    "up_progress": "📤 {msg}",
    "up_done": "🎉 آپلود کامل شد!\nکامیت: <code>{sha}</code>\n🔗 {url}",
    "up_fail": "❌ آپلود ناموفق: <code>{error}</code>",
    "up_secrets_offer": (
        "🔐 ورک‌فلوها به این سکرت‌ها ارجاع می‌دهند:\n{list}\n\n"
        "در ریپو وجود ندارد: <b>{missing}</b>\nروی هر سکرت بزنید تا همین حالا تنظیمش کنید."
    ),
    "up_secrets_all_present": "✅ همهٔ سکرت‌های ارجاع‌شده از قبل در ریپو وجود دارند.",

    "sec_pick_repo": "🔐 <b>سکرت‌ها</b>\nیک ریپو انتخاب کنید:",
    "sec_title": "🔐 <b>سکرت‌های {full}</b> ({n})\n{list}\n\nروی سکرت بزنید تا به‌روزرسانی/حذف کنید، یا سکرت جدید بسازید.",
    "sec_item": "• <code>{name}</code> — به‌روزرسانی {updated}",
    "sec_none": "<i>هنوز سکرتی نیست</i>",
    "btn_sec_add": "➕ سکرت جدید",
    "btn_sec_scan": "🔎 تشخیص از ورک‌فلوها",
    "btn_sec_vars": "📋 متغیرها",
    "sec_ask_name": "🔐 <b>نام سکرت</b> را بفرستید (A-Z، 0-9، _):",
    "sec_name_bad": "❌ نام نامعتبر است. از حروف بزرگ، ارقام و زیرخط استفاده کنید؛ نباید با GITHUB_ شروع شود.",
    "sec_ask_value": "🔑 <b>مقدار</b> <code>{name}</code> را بفرستید.\n<i>پیام شما بلافاصله بعد از خواندن حذف می‌شود.</i>",
    "sec_saved": "✅ سکرت <code>{name}</code> در <b>{full}</b> ذخیره شد (با کلید عمومی ریپو رمزنگاری شد).",
    "sec_deleted": "🗑 سکرت <code>{name}</code> حذف شد.",
    "sec_actions": "🔐 <code>{name}</code> در <b>{full}</b>",
    "btn_sec_update": "✏️ به‌روزرسانی مقدار",
    "btn_sec_delete": "🗑 حذف",
    "sec_detect_result": "🔎 ورک‌فلوها ارجاع می‌دهند به: {all}\nموجود نیست: <b>{missing}</b>",
    "sec_detect_none": "🔎 فایل ورک‌فلویی در این ریپو پیدا نشد.",
    "vars_title": "📋 <b>متغیرهای {full}</b>\n{list}",
    "vars_item": "• <code>{name}</code> = <code>{value}</code>",
    "btn_var_add": "➕ متغیر جدید",
    "var_ask_name": "📋 <b>نام متغیر</b> را بفرستید:",
    "var_ask_value": "📋 <b>مقدار</b> <code>{name}</code> را بفرستید:",
    "var_saved": "✅ متغیر <code>{name}</code> ذخیره شد.",

    "act_pick_repo": "⚙️ <b>Actions</b>\nیک ریپو انتخاب کنید:",
    "act_title": "⚙️ <b>Actions — {full}</b>\n\n<b>ورک‌فلوها:</b>\n{workflows}\n\n<b>اجراهای اخیر:</b>\n{runs}",
    "act_wf_item": "• {name} <code>{file}</code> [{state}]",
    "act_run_item": "{icon} #{num} {name} — {status} {conclusion} · {branch} · {age}",
    "act_none": "<i>هیچ</i>",
    "btn_act_dispatch": "▶️ اجرای ورک‌فلو",
    "btn_act_runs": "📜 اجراها",
    "btn_act_running": "🏃 در حال اجرا",
    "act_pick_wf": "▶️ کدام ورک‌فلو اجرا شود؟",
    "act_pick_ref": "🌿 روی کدام برنچ؟ (نام بفرستید یا پیش‌فرض <code>{branch}</code>):",
    "act_dispatched": "▶️ <b>{wf}</b> روی <code>{ref}</code> اجرا شد. پیشرفتش را به شما اطلاع می‌دهم.",
    "act_dispatch_fail": "❌ اجرا ناموفق: <code>{error}</code>\n<i>ورک‌فلو باید تریگر <code>workflow_dispatch</code> داشته باشد.</i>",
    "act_run_card": (
        "{icon} <b>اجرای #{num}</b> — {name}\nوضعیت: <b>{status}</b> {conclusion}\n"
        "🌿 {branch} · {event} · {age}\n🔗 {url}\n\n<b>جاب‌ها:</b>\n{jobs}"
    ),
    "act_job_item": "{icon} {name} — {status} {conclusion}",
    "btn_run_cancel": "⏹ لغو اجرا",
    "btn_run_rerun": "🔁 اجرای مجدد",
    "btn_run_rerun_failed": "🔁 اجرای مجدد ناموفق‌ها",
    "btn_run_logs": "📄 آخرین لاگ",
    "act_cancelled": "⏹ درخواست لغو برای اجرای #{num} ثبت شد.",
    "act_rerun": "🔁 درخواست اجرای مجدد برای #{num} ثبت شد.",
    "act_logs": "📄 <b>انتهای لاگ — {job}</b>\n<pre>{log}</pre>",
    "act_running_global": "🏃 <b>جاب‌های در حال اجرا در کل اکانت</b>\n{list}",
    "act_running_none": "😴 الان چیزی در حال اجرا نیست.",

    "notif_title": "🔔 <b>اعلان‌های اخیر</b>\n{list}",
    "notif_none": "<i>هنوز اعلانی نیست</i>",
    "notif_item": "<code>{time}</code> {text}",
    "jobs_title": "🧾 <b>کارهای اخیر</b>\n{list}",
    "job_item": "{icon} <b>{title}</b> — {status} ({steps} مرحله)",

    "settings_title": (
        "⚙️ <b>تنظیمات</b>\n"
        "زبان: {lang}\nگیت‌هاب: {login} ({level})\nAI: {ai}\nدنبال‌شده‌ها: {watches}\n"
        "محیط اجرا: {runtime}"
    ),
    "btn_change_lang": "🌐 زبان",
    "btn_change_token": "🔑 تغییر توکن گیت‌هاب",
    "btn_ai_reset": "🤖 پیکربندی مجدد AI",
    "btn_export": "💾 ذخیرهٔ وضعیت",
    "btn_restart": "♻️ ری‌استارت ربات (اجرای جدید)",
    "export_done": "💾 نقطهٔ بازیابی وضعیت پوش شد.",
    "export_fail": "❌ ذخیرهٔ وضعیت ناموفق: {error}",
    "restart_confirm": "♻️ همین حالا به یک اجرای جدید ورک‌فلو منتقل شوم؟ هیچ چیزی از دست نمی‌رود — اول وضعیت ذخیره می‌شود.",
    "restart_go": "♻️ در حال انتقال… تا ۳۰–۶۰ ثانیهٔ دیگر از اجرای جدید پیام می‌دهم.",
    "restart_not_actions": "ℹ️ داخل GitHub Actions نیستیم؛ ری‌استارت به صورت ری‌استارت پروسهٔ محلی انجام می‌شود.",

    "lifecycle_hello": "🟢 <b>ربات آنلاین شد</b> — اجرای <code>#{run}</code> (تلاش {attempt}).\nوضعیت بازیابی شد: {restored}. بودجهٔ زمان: {minutes} دقیقه.",
    "lifecycle_bye": "🟠 بودجهٔ زمان این اجرا تمام شد. وضعیت ذخیره و اجرای جدید شروع می‌شود… حدود ۱ دقیقهٔ دیگر برمی‌گردم.",
    "lifecycle_resume_ai": "♻️ ادامهٔ کار نیمه‌تمام GITHUB_AI از همان‌جایی که متوقف شد…",
    "lifecycle_no_pat": "⚠️ سکرت <code>GH_PAT</code> موجود نیست — نمی‌توانم وضعیت را ذخیره یا خودم را ری‌استارت کنم. آن را در سکرت‌های ریپوی میزبان تنظیم کنید.",

    "ai_setup_base": (
        "🤖 <b>راه‌اندازی GITHUB_AI</b>\n\nمرحلهٔ ۱/۳ — <b>BASE_URL</b> یک API سازگار با OpenAI را بفرستید "
        "(مثلاً <code>https://api.openai.com/v1</code> یا <code>https://openrouter.ai/api/v1</code>):"
    ),
    "ai_setup_key": "مرحلهٔ ۲/۳ — <b>API_KEY</b> را بفرستید.\n<i>پیام شما بعد از خواندن حذف می‌شود.</i>",
    "ai_fetching_models": "🔎 در حال دریافت لیست مدل‌ها از <code>{base}</code>…",
    "ai_models_fail": "❌ لیست مدل‌ها دریافت نشد: <code>{error}</code>\nنام مدل را دستی بفرستید یا /cancel.",
    "ai_pick_model": "مرحلهٔ ۳/۳ — یک <b>مدل</b> انتخاب کنید ({n} مدل، صفحهٔ {page}/{pages}) یا نامش را بفرستید:",
    "ai_ready": "✅ GITHUB_AI آماده است.\nBase: <code>{base}</code>\nمدل: <code>{model}</code>\n\nهر چیزی بخواهید بفرستید — این پروژه را کامل می‌شناسم.",
    "ai_home": (
        "🤖 <b>GITHUB_AI</b> — مدل <code>{model}</code>\n"
        "نشست: <code>{session}</code> · {msgs} پیام · {compressions} فشرده‌سازی\n"
        "حافظه: {mem} مورد · مهارت‌ها: {skills}\n\n"
        "فقط درخواست‌تان را بنویسید. ابزارها: ترمینال، فایل‌ها، GitHub API، جستجوی وب{search}، حافظه، مهارت‌ها، لیست کارها."
    ),
    "btn_ai_new": "🆕 نشست جدید",
    "btn_ai_sessions": "🗂 نشست‌ها",
    "btn_ai_memory": "🧠 حافظه",
    "btn_ai_skills": "🧩 مهارت‌ها",
    "btn_ai_model": "🔄 تغییر مدل",
    "btn_ai_stop": "⏹ توقف",
    "ai_new_session": "🆕 نشست جدید <code>{id}</code> شروع شد.",
    "ai_thinking": "🤖 در حال فکر کردن…",
    "ai_tool_call": "🔧 <code>{tool}</code> {args}",
    "ai_tool_result": "↩️ {tool}: {summary}",
    "ai_rate_limited": "⏳ مدل به محدودیت نرخ خورد — {secs} ثانیه صبر می‌کنم و همان مرحله را ادامه می‌دهم (تلاش {n}).",
    "ai_api_error": "⚠️ خطای API: <code>{error}</code> — تلاش مجدد تا {secs} ثانیه دیگر.",
    "ai_compressing": "🗜 کانتکست بزرگ شده — نوبت‌های قدیمی فشرده می‌شوند (چیزی از دست نمی‌رود؛ یک خلاصه جایگزین می‌شود).",
    "ai_done": "✅ انجام شد ({iters} مرحله، {tools} فراخوانی ابزار).",
    "ai_stopped": "⏹ متوقف شد.",
    "ai_busy": "⏳ GITHUB_AI هنوز روی درخواست قبلی‌تان کار می‌کند. برای قطع، «توقف» را بزنید.",
    "ai_not_configured": "🤖 GITHUB_AI هنوز پیکربندی نشده. روی 🤖 GITHUB_AI بزنید تا BASE_URL، API_KEY و مدل را تنظیم کنید.",
    "ai_sessions_title": "🗂 <b>نشست‌ها</b>\n{list}",
    "ai_session_item": "{active} <code>{id}</code> {title} — {msgs} پیام",
    "ai_memory_title": "🧠 <b>حافظه</b>\n<b>MEMORY</b>\n{memory}\n\n<b>USER</b>\n{user}",
    "ai_memory_empty": "<i>خالی</i>",
    "ai_skills_title": "🧩 <b>مهارت‌ها</b>\n{list}",
    "ai_skill_item": "• <code>{name}</code> — {desc}",
    "ai_max_iter": "⚠️ به سقف مراحل ({n}) رسیدم. برای ادامه «continue» بفرستید.",
"ai_file_received": "📎 <b>{name}</b> دریافت شد — بگو باهاش چیکار کنم.",

    "help_text": "HELP_PLACEHOLDER",
    "btn_help_arch": "🏗 معماری",
    "btn_help_ai": "🤖 GITHUB_AI",
    "btn_help_cmds": "⌨️ دستورات",
    "btn_help_security": "🔒 امنیت",

    "error_generic": "❌ خطا: <code>{error}</code>",
    "gh_wait": "⏳ محدودیت نرخ گیت‌هاب — {secs} ثانیه صبر و سپس ادامه…",
    "unknown": "🤔 متوجه نشدم. از منو یا /help استفاده کنید.",
    "ok": "👌",
    "yes": "بله",
    "no": "خیر",
    "public": "🌍 عمومی",
    "private": "🔒 خصوصی",
    "none": "هیچ",
}
