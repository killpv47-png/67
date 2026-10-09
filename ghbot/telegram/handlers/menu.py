"""Main menu routing: reply-keyboard text buttons, slash commands, notifications list, cancel."""

from __future__ import annotations

import json

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...i18n import LANGS, t
from ..app import AppContext
from ..keyboards import back_menu, main_inline
from ..utils import edit_or_send, esc, hhmm
from .onboarding import run_scan, show_menu

router = Router(name="menu")


def _button_keys() -> dict[str, str]:
    """Reverse map of every language's button label -> key, so reply-keyboard taps work in all 10 languages."""
    out = {}
    for table in LANGS.values():
        for key in ("btn_repos", "btn_new_repo", "btn_upload", "btn_actions", "btn_secrets", "btn_ai", "btn_scan",
                    "btn_notifs", "btn_settings", "btn_help"):
            if key in table:
                out[table[key]] = key
    return out


BUTTONS = _button_keys()
ROUTE = {
    "btn_repos": "repos:list:0", "btn_new_repo": "nr:start", "btn_upload": "up:pick:0", "btn_actions": "act:pick:0",
    "btn_secrets": "sec:pick:0", "btn_ai": "ai:home", "btn_scan": "scan:run", "btn_notifs": "notif:list",
    "btn_settings": "set:home", "btn_help": "help:home",
}


@router.message(Command("menu"))
async def cmd_menu(msg: Message, state: FSMContext, app: AppContext):
    await state.clear()
    await show_menu(msg, app, msg.from_user.id)


@router.message(Command("cancel"))
async def cmd_cancel(msg: Message, state: FSMContext, lang: str):
    await state.clear()
    await msg.answer(t(lang, "cancelled"), reply_markup=main_inline(lang))


@router.callback_query(F.data == "flow:cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await edit_or_send(cb, t(lang, "cancelled"), main_inline(lang))


@router.callback_query(F.data == "menu:home")
async def cb_menu(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    await state.clear()
    await edit_or_send(cb, "🏠", main_inline(lang))


@router.message(Command("scan"))
async def cmd_scan(msg: Message, app: AppContext, lang: str):
    await run_scan(msg, app, msg.from_user.id, lang)


@router.callback_query(F.data == "scan:run")
async def cb_scan(cb: CallbackQuery, app: AppContext, lang: str):
    await run_scan(cb.message, app, cb.from_user.id, lang)


@router.message(Command("notifications", "notifs", "jobs"))
async def cmd_notifs(msg: Message, app: AppContext, lang: str):
    await _notifs(msg, app, msg.from_user.id, lang)


@router.callback_query(F.data == "notif:list")
async def cb_notifs(cb: CallbackQuery, app: AppContext, lang: str):
    await _notifs(cb, app, cb.from_user.id, lang)


async def _notifs(event, app: AppContext, tg_id: int, lang: str):
    rows = await app.db.recent_notifications(tg_id, 15)
    body = "\n".join(t(lang, "notif_item", time=hhmm(r["created_at"]), text=r["text"][:160]) for r in rows) or t(lang, "notif_none")
    jobs = await app.db.recent_jobs(tg_id, 5)
    icon = {"done": "✅", "failed": "❌", "running": "🔄"}
    jbody = "\n".join(t(lang, "job_item", icon=icon.get(j["status"], "•"), title=esc(j["title"]), status=j["status"],
                        steps=len(json.loads(j["steps"]))) for j in jobs)
    text = t(lang, "notif_title", list=body)
    if jbody:
        text += "\n\n" + t(lang, "jobs_title", list=jbody)
    await edit_or_send(event, text[:4000], back_menu(lang))


# Reply-keyboard taps (any language) — must be registered LAST among text handlers in this router
@router.message(F.text.in_(set(BUTTONS)))
async def reply_buttons(msg: Message, state: FSMContext, app: AppContext, lang: str, dispatcher_route=None):
    key = BUTTONS[msg.text]
    await state.clear()
    if key == "btn_scan":
        await run_scan(msg, app, msg.from_user.id, lang)
        return
    if key == "btn_notifs":
        await _notifs(msg, app, msg.from_user.id, lang)
        return
    # Dispatch to the same inline callback handlers by synthesizing a tap
    from .router_bridge import dispatch_callback
    await dispatch_callback(msg, ROUTE[key], app, lang, state)
