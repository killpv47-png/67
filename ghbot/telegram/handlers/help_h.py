"""Docs button: full architecture + how the bot works, in EN and FA (other languages get EN)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...i18n import t
from ..app import AppContext
from ..keyboards import ib, rows
from ..utils import edit_or_send
from .router_bridge import entry

router = Router(name="help")

DOCS = {
    "en": {
        "home": (
            "📖 <b>GitHub Control Bot — Documentation</b>\n\n"
            "This bot runs as a long-lived job inside <b>GitHub Actions</b> and lets you manage your GitHub account from "
            "Telegram. It restarts itself before the 6-hour job limit and carries all state (encrypted) into the next run.\n\n"
            "Pick a section:"
        ),
        "arch": (
            "🏗 <b>Architecture</b>\n\n"
            "<b>Runtime</b>: Python 3.12 · aiogram 3 (long polling, async) · SQLite (WAL + FTS5) · httpx\n\n"
            "<b>Modules</b>\n"
            "• <code>core/</code> config, AES-256-GCM crypto, DB, redaction, notifier\n"
            "• <code>github/</code> REST client (retry, rate-limit sleep, Git Data bulk commit, sealed-box secrets), access levels, scanner, ZIP analysis\n"
            "• <code>telegram/</code> handlers: repos, new-repo wizard, upload, secrets, actions, settings, AI\n"
            "• <code>ai/</code> GITHUB_AI (Hermes architecture)\n"
            "• <code>lifecycle/</code> checkpoint + handoff\n\n"
            "<b>Access levels</b> (from token scopes): 👑 GOD · 🏛 ARCHITECT · 🛠 ENGINEER · 💻 DEVELOPER · 👁 OBSERVER · 👻 GHOST\n\n"
            "<b>Lifecycle</b>\n"
            "1. Run starts → restores <code>state/state.enc</code> from branch <code>ghbot-state</code> of the host repo (decrypted with STATE_KEY)\n"
            "2. Every 2 min (if changed) the DB is re-encrypted and pushed\n"
            "3. At MAX_RUN_MINUTES (default 330) → final checkpoint → <code>workflow_dispatch</code> via GH_PAT → exit\n"
            "4. The workflow <code>concurrency</code> group makes the new run wait, so there is never a double poller\n"
            "5. A cron watchdog (every 30 min) restarts the bot if it ever dies\n\n"
            "<b>Notifications</b>: every step of every job is sent to you and stored (🔔 Notifications)."
        ),
        "ai": (
            "🤖 <b>GITHUB_AI</b>\n\n"
            "A Hermes-Agent-style agent that lives inside this project and knows it as its home.\n\n"
            "<b>Setup</b>: BASE_URL → API_KEY → the bot fetches <code>/models</code> and you pick one.\n\n"
            "<b>Prompt (3 tiers, frozen per session for cache)</b>\n"
            "• stable: SOUL.md identity, memory/skills/tool-use/execution guidance, Telegram hint\n"
            "• context: AGENTS.md (module map, where every secret lives, how to change things)\n"
            "• volatile: skills index, MEMORY + USER snapshot, session line, runtime environment\n\n"
            "<b>Tools</b>: terminal · read_file/write_file/patch/search_files · github_api (30+ actions, your token) · "
            "web_search/web_extract (Tavily) · memory · skills_list/skill_view/skill_manage · session_search · todo_list\n\n"
            "<b>Memory</b>: MEMORY (environment facts) + USER (profile), char-budgeted, persisted in DB.\n"
            "<b>Skills</b>: <code>ai/home/skills/*/SKILL.md</code> — loaded on demand, created/patched by the agent, checkpointed with state.\n"
            "<b>Context compression</b>: at 50% of the window, old tool outputs are pruned, then middle turns are summarized into a structured checkpoint (Hermes template).\n"
            "<b>Rate limits</b>: 429/5xx → wait (Retry-After aware) and resume the <i>same</i> request. The in-flight step is persisted, so even a workflow restart resumes it.\n"
            "<b>Step-by-step</b>: 3+ step tasks go through todo_list; you see the plan and each ✅ live."
        ),
        "cmds": (
            "⌨️ <b>Commands</b>\n\n"
            "/start — onboarding / menu\n/menu — main menu\n/lang — change language\n/token — set GitHub token\n"
            "/scan — rescan account\n/repos — list repos\n/repo owner/name — repo card\n/newrepo — create repo wizard\n"
            "/upload [owner/name] — upload ZIP\n/secrets [owner/name] — secrets\n/actions [owner/name] — Actions\n"
            "/ai &lt;text&gt; — ask GITHUB_AI\n/ai_new — new AI session\n/ai_stop — stop the agent\n"
            "/notifications — recent notifications & jobs\n/settings — settings\n/restart — hand off to a new run\n"
            "/help — this\n/cancel — cancel current flow\n\n"
            "Everything is also reachable from the reply keyboard and inline buttons. "
            "When GITHUB_AI is configured, any plain text that is not a command or button goes to the agent."
        ),
        "sec": (
            "🔒 <b>Security</b>\n\n"
            "• Your GitHub token is encrypted (AES-256-GCM, scrypt KDF from STATE_KEY) before it is stored; the whole DB is encrypted again before leaving the runner.\n"
            "• Messages containing tokens/secret values are deleted from the chat immediately after reading.\n"
            "• Every outgoing message, log line, AI tool result and compaction summary passes through a redactor.\n"
            "• Repo secrets are sealed with the repo's libsodium public key — GitHub never returns them, and neither does the bot.\n"
            "• The bot locks to OWNER_IDS (or the first user who starts it).\n"
            "• GITHUB_AI cannot read <code>.env</code>, <code>ghbot.db</code> or <code>state.enc</code>, cannot export protected env vars, and is blocked from catastrophic shell commands.\n"
            "• Destructive actions (delete repo, replace all files, delete secret) require explicit confirmation."
        ),
    },
    "fa": {
        "home": (
            "📖 <b>ربات کنترل گیت‌هاب — توضیحات</b>\n\n"
            "این ربات به‌صورت یک جاب طولانی داخل <b>GitHub Actions</b> اجرا می‌شود و به شما اجازه می‌دهد اکانت گیت‌هاب‌تان را از تلگرام مدیریت کنید. "
            "قبل از رسیدن به سقف ۶ ساعتهٔ جاب خودش را ری‌استارت می‌کند و تمام وضعیت (رمزنگاری‌شده) را به اجرای بعدی منتقل می‌کند.\n\n"
            "یک بخش انتخاب کنید:"
        ),
        "arch": (
            "🏗 <b>معماری</b>\n\n"
            "<b>محیط اجرا</b>: Python 3.12 · aiogram 3 (long polling، async) · SQLite (WAL + FTS5) · httpx\n\n"
            "<b>ماژول‌ها</b>\n"
            "• <code>core/</code> تنظیمات، رمزنگاری AES-256-GCM، دیتابیس، حذف اطلاعات حساس، سیستم اعلان\n"
            "• <code>github/</code> کلاینت REST (تلاش مجدد، صبر روی rate-limit، کامیت گروهی Git Data، سکرت‌های sealed-box)، سطوح دسترسی، اسکنر، تحلیل ZIP\n"
            "• <code>telegram/</code> هندلرها: ریپوها، ویزارد ساخت ریپو، آپلود، سکرت‌ها، Actions، تنظیمات، AI\n"
            "• <code>ai/</code> GITHUB_AI (معماری Hermes)\n"
            "• <code>lifecycle/</code> نقطهٔ بازیابی + انتقال اجرا\n\n"
            "<b>سطوح دسترسی</b> (از اسکوپ‌های توکن): 👑 GOD · 🏛 ARCHITECT · 🛠 ENGINEER · 💻 DEVELOPER · 👁 OBSERVER · 👻 GHOST\n\n"
            "<b>چرخهٔ حیات</b>\n"
            "۱. اجرا شروع می‌شود → <code>state/state.enc</code> از برنچ <code>ghbot-state</code> ریپوی میزبان بازیابی می‌شود (رمزگشایی با STATE_KEY)\n"
            "۲. هر ۲ دقیقه (در صورت تغییر) دیتابیس دوباره رمزنگاری و پوش می‌شود\n"
            "۳. در MAX_RUN_MINUTES (پیش‌فرض ۳۳۰) → ذخیرهٔ نهایی → <code>workflow_dispatch</code> با GH_PAT → خروج\n"
            "۴. گروه <code>concurrency</code> ورک‌فلو باعث می‌شود اجرای جدید صبر کند، پس هیچ‌وقت دو poller هم‌زمان نداریم\n"
            "۵. یک cron نگهبان (هر ۳۰ دقیقه) اگر ربات بمیرد دوباره بالا می‌آوردش\n\n"
            "<b>اعلان‌ها</b>: هر مرحلهٔ هر کار برای شما ارسال و ذخیره می‌شود (🔔 اعلان‌ها)."
        ),
        "ai": (
            "🤖 <b>GITHUB_AI</b>\n\n"
            "یک ایجنت با معماری Hermes Agent که داخل همین پروژه زندگی می‌کند و آن را مثل خانهٔ خودش می‌شناسد.\n\n"
            "<b>راه‌اندازی</b>: BASE_URL → API_KEY → ربات <code>/models</code> را می‌گیرد و شما یکی را انتخاب می‌کنید.\n\n"
            "<b>پرامپت (۳ لایه، برای کش در هر نشست ثابت)</b>\n"
            "• stable: هویت SOUL.md، راهنمای حافظه/مهارت/ابزار/اجرا، نکتهٔ تلگرام\n"
            "• context: AGENTS.md (نقشهٔ ماژول‌ها، محل هر سکرت، نحوهٔ تغییر هر چیز)\n"
            "• volatile: فهرست مهارت‌ها، اسنپ‌شات MEMORY + USER، خط نشست، محیط اجرا\n\n"
            "<b>ابزارها</b>: terminal · read_file/write_file/patch/search_files · github_api (۳۰+ عملیات با توکن شما) · "
            "web_search/web_extract (Tavily) · memory · skills_list/skill_view/skill_manage · session_search · todo_list\n\n"
            "<b>حافظه</b>: MEMORY (واقعیت‌های محیط) + USER (پروفایل)، با بودجهٔ کاراکتری، ذخیره در دیتابیس.\n"
            "<b>مهارت‌ها</b>: <code>ai/home/skills/*/SKILL.md</code> — بر اساس نیاز لود می‌شوند، توسط ایجنت ساخته/اصلاح می‌شوند و همراه وضعیت ذخیره می‌شوند.\n"
            "<b>فشرده‌سازی کانتکست</b>: در ۵۰٪ پنجره، خروجی ابزارهای قدیمی حذف و سپس نوبت‌های میانی به یک خلاصهٔ ساخت‌یافته (قالب Hermes) تبدیل می‌شوند.\n"
            "<b>محدودیت نرخ</b>: 429/5xx → صبر (با رعایت Retry-After) و ادامهٔ <i>همان</i> درخواست. مرحلهٔ در حال اجرا ذخیره می‌شود، پس حتی ری‌استارت ورک‌فلو هم آن را ادامه می‌دهد.\n"
            "<b>مرحله‌ای</b>: کارهای ۳+ مرحله‌ای از todo_list می‌گذرند؛ برنامه و هر ✅ را زنده می‌بینید."
        ),
        "cmds": (
            "⌨️ <b>دستورات</b>\n\n"
            "/start — شروع / منو\n/menu — منوی اصلی\n/lang — تغییر زبان\n/token — تنظیم توکن گیت‌هاب\n"
            "/scan — اسکن مجدد اکانت\n/repos — لیست ریپوها\n/repo owner/name — کارت ریپو\n/newrepo — ویزارد ساخت ریپو\n"
            "/upload [owner/name] — آپلود ZIP\n/secrets [owner/name] — سکرت‌ها\n/actions [owner/name] — Actions\n"
            "/ai &lt;متن&gt; — پرسش از GITHUB_AI\n/ai_new — نشست جدید AI\n/ai_stop — توقف ایجنت\n"
            "/notifications — اعلان‌ها و کارهای اخیر\n/settings — تنظیمات\n/restart — انتقال به اجرای جدید\n"
            "/help — همین\n/cancel — لغو جریان فعلی\n\n"
            "همهٔ این‌ها از کیبورد پایین و دکمه‌های شیشه‌ای هم در دسترس‌اند. "
            "وقتی GITHUB_AI پیکربندی شده باشد، هر پیام متنی که دستور یا دکمه نباشد به ایجنت می‌رود."
        ),
        "sec": (
            "🔒 <b>امنیت</b>\n\n"
            "• توکن گیت‌هاب شما قبل از ذخیره رمزنگاری می‌شود (AES-256-GCM، کلید از STATE_KEY با scrypt)؛ کل دیتابیس هم قبل از خروج از runner دوباره رمزنگاری می‌شود.\n"
            "• پیام‌های حاوی توکن/مقدار سکرت بلافاصله بعد از خواندن از چت حذف می‌شوند.\n"
            "• هر پیام خروجی، خط لاگ، نتیجهٔ ابزار AI و خلاصهٔ فشرده‌سازی از یک redactor می‌گذرد.\n"
            "• سکرت‌های ریپو با کلید عمومی libsodium ریپو مهر می‌شوند — گیت‌هاب هرگز آن‌ها را برنمی‌گرداند، ربات هم همین‌طور.\n"
            "• ربات به OWNER_IDS (یا اولین کاربری که استارت می‌زند) قفل می‌شود.\n"
            "• GITHUB_AI نمی‌تواند <code>.env</code>، <code>ghbot.db</code> یا <code>state.enc</code> را بخواند، نمی‌تواند متغیرهای محافظت‌شده را export کند و دستورات فاجعه‌بار شل برایش مسدود است.\n"
            "• عملیات مخرب (حذف ریپو، جایگزینی همهٔ فایل‌ها، حذف سکرت) نیاز به تأیید صریح دارند."
        ),
    },
}


def _docs(lang: str) -> dict:
    return DOCS.get(lang, DOCS["en"])


def _kb(lang: str):
    return rows(
        [ib(t(lang, "btn_help_arch"), "help:arch"), ib(t(lang, "btn_help_ai"), "help:ai")],
        [ib(t(lang, "btn_help_cmds"), "help:cmds"), ib(t(lang, "btn_help_security"), "help:sec")],
        [ib(t(lang, "btn_menu"), "menu:home")],
    )


@entry("help:home")
async def entry_help(msg: Message, app: AppContext, lang: str, state: FSMContext):
    await msg.answer(_docs(lang)["home"], reply_markup=_kb(lang), parse_mode="HTML")


@router.message(Command("help"))
async def cmd_help(msg: Message, lang: str):
    await msg.answer(_docs(lang)["home"], reply_markup=_kb(lang), parse_mode="HTML")


@router.callback_query(F.data.startswith("help:"))
async def cb_help(cb: CallbackQuery, lang: str):
    section = cb.data.split(":")[1]
    await edit_or_send(cb, _docs(lang).get(section, _docs(lang)["home"]), _kb(lang))
