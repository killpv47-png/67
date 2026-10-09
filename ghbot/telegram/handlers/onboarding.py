"""/start → language → GitHub token → account scan → main menu."""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...github.access import LEVELS
from ...github.client import GitHubClient, GitHubError
from ...github.scanner import scan_account
from ...i18n import LANG_NAMES, t
from ..app import AppContext
from ..keyboards import lang_keyboard, main_inline, main_reply_keyboard, persist_repo_ids, register_repos
from ..states import Onboard
from ..utils import esc, safe_delete

router = Router(name="onboarding")
TOKEN_RE = re.compile(r"^(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|[a-f0-9]{40})$")


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext, app: AppContext, user_row):
    await state.clear()
    if not user_row["gh_token_enc"]:
        await state.set_state(Onboard.lang)
        await msg.answer(t("en", "choose_lang"), reply_markup=lang_keyboard(), parse_mode="HTML")
    else:
        await show_menu(msg, app, user_row["tg_id"])


@router.message(Command("lang", "language"))
async def cmd_lang(msg: Message, state: FSMContext):
    await msg.answer(t("en", "choose_lang"), reply_markup=lang_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("lang:set:"))
async def cb_lang(cb: CallbackQuery, state: FSMContext, app: AppContext, user_row):
    code = cb.data.split(":")[2]
    if code not in LANG_NAMES:
        return
    await app.db.set_user_fields(cb.from_user.id, lang=code)
    await cb.message.edit_text(t(code, "lang_set", lang=LANG_NAMES[code]), parse_mode="HTML")
    if not user_row["gh_token_enc"]:
        await state.set_state(Onboard.token)
        await cb.message.answer(t(code, "welcome"), parse_mode="HTML", disable_web_page_preview=True)
    else:
        await show_menu(cb.message, app, cb.from_user.id)


@router.message(Command("token"))
async def cmd_token(msg: Message, state: FSMContext, lang: str):
    await state.set_state(Onboard.token)
    await msg.answer(t(lang, "send_token"), parse_mode="HTML")


@router.message(Onboard.token, F.text)
async def got_token(msg: Message, state: FSMContext, app: AppContext, lang: str):
    token = (msg.text or "").strip()
    await safe_delete(msg)  # never leave the token in chat history
    if not TOKEN_RE.match(token):
        await msg.answer(t(lang, "token_invalid"), parse_mode="HTML")
        return
    status = await msg.answer(t(lang, "token_checking"), parse_mode="HTML")
    gh = GitHubClient(token)
    try:
        me = await gh.me()
    except GitHubError as e:
        await gh.aclose()
        await status.edit_text(t(lang, "token_bad", error=esc(e.message)), parse_mode="HTML")
        return
    await app.save_token(msg.from_user.id, token)
    await app.db.set_user_fields(msg.from_user.id, gh_login=me.get("login"))
    await state.clear()
    await status.edit_text(t(lang, "token_saved"), parse_mode="HTML")
    await run_scan(msg, app, msg.from_user.id, lang, gh)
    await show_menu(msg, app, msg.from_user.id)


async def run_scan(msg: Message, app: AppContext, tg_id: int, lang: str, gh: GitHubClient | None = None):
    own = gh is None
    if own:
        gh = await app.gh(tg_id)
        if not gh:
            await msg.answer(t(lang, "need_token"), parse_mode="HTML")
            return
    status = await msg.answer(t(lang, "scan_step", step="identity"), parse_mode="HTML")

    async def progress(step: str):
        await app.notifier.edit(msg.chat.id, status.message_id, t(lang, "scan_step", step=step), min_interval=0.4)

    try:
        res = await scan_account(gh, progress=progress)
    except GitHubError as e:
        await status.edit_text(t(lang, "error_generic", error=esc(e.message)), parse_mode="HTML")
        return
    finally:
        await gh.aclose()
    level = res.level or LEVELS["GHOST"]
    await app.db.set_user_fields(tg_id, gh_login=res.login, gh_scopes=",".join(res.scopes or []), access_level=level.name)
    app.repo_cache[tg_id] = res.repos
    register_repos(res.repos)
    await persist_repo_ids(app.db)
    pub = sum(1 for r in res.repos if not r["private"])
    scopes = t(lang, "fine_grained") if res.fine_grained else (", ".join(res.scopes) if res.scopes else "—")
    text = t(lang, "scan_report", login=esc(res.login), name=f"({esc(res.name)})" if res.name else "",
             repos=len(res.repos), pub=pub, priv=len(res.repos) - pub, orgs=", ".join(res.orgs) or "—",
             running=len(res.running), rate_rem=res.rate.get("remaining", "?"), rate_lim=res.rate.get("limit", "?"),
             level_emoji=level.emoji, level=level.name, level_desc=t(lang, level.description_key), scopes=esc(scopes))
    if res.running:
        text += "\n\n" + "\n".join(t(lang, "scan_running_item", repo=esc(r["repo"]), name=esc(r.get("name", "")),
                                     status=r.get("status", "")) for r in res.running[:15])
    if res.errors:
        text += "\n\n" + t(lang, "scan_errors", errors=esc("; ".join(res.errors)))
    await status.edit_text(text, parse_mode="HTML", disable_web_page_preview=True)
    await app.db.add_notification(tg_id, "scan", f"Account scan: {len(res.repos)} repos, level {level.name}")


async def show_menu(msg: Message, app: AppContext, tg_id: int):
    u = await app.db.get_user(tg_id)
    lang = u["lang"] or "en"
    level = LEVELS.get(u["access_level"] or "", LEVELS["GHOST"])
    await msg.answer(t(lang, "menu_title", login=esc(u["gh_login"] or "?"), level_emoji=level.emoji),
                     reply_markup=main_reply_keyboard(lang), parse_mode="HTML")
    await msg.answer("👇", reply_markup=main_inline(lang))
