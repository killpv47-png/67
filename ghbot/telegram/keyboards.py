"""Inline + reply keyboards.  Callback data is compact: ``ns:action:arg``."""

from __future__ import annotations

import hashlib

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from ..i18n import LANG_NAMES, t

# Telegram limits callback_data to 64 bytes, so repo names are referenced by a short hash.
# The map is mirrored into the DB (kv "repo_ids") so buttons in old messages keep working
# after a workflow restart; see ``persist_repo_ids`` / ``load_repo_ids``.
_REPO_IDS: dict[str, str] = {}
_DIRTY: set[str] = set()


def rid(full: str) -> str:
    h = hashlib.sha1(full.encode()).hexdigest()[:10]
    if h not in _REPO_IDS:
        _REPO_IDS[h] = full
        _DIRTY.add(h)
    return h


def repo_from_id(h: str) -> str | None:
    return _REPO_IDS.get(h)


async def load_repo_ids(db) -> None:
    try:
        _REPO_IDS.update(await db.kv_get("repo_ids", {}) or {})
    except Exception:
        pass


async def persist_repo_ids(db) -> None:
    """Flush newly seen hashes to the DB (cheap; called from the checkpoint loop and after scans)."""
    if not _DIRTY:
        return
    try:
        await db.kv_set("repo_ids", _REPO_IDS)
        _DIRTY.clear()
    except Exception:
        pass


def register_repos(repos: list[dict]) -> None:
    for r in repos:
        rid(r["full_name"])


def ib(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data[:64])


def rows(*btns: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in btns if r])


def lang_keyboard() -> InlineKeyboardMarkup:
    items = list(LANG_NAMES.items())
    return InlineKeyboardMarkup(inline_keyboard=[
        [ib(name, f"lang:set:{code}") for code, name in items[i:i + 2]] for i in range(0, len(items), 2)
    ])


def main_reply_keyboard(lang: str) -> ReplyKeyboardMarkup:
    k = lambda key: KeyboardButton(text=t(lang, key))  # noqa: E731
    return ReplyKeyboardMarkup(
        keyboard=[
            [k("btn_repos"), k("btn_new_repo"), k("btn_upload")],
            [k("btn_actions"), k("btn_secrets"), k("btn_ai")],
            [k("btn_scan"), k("btn_notifs"), k("btn_settings"), k("btn_help")],
        ],
        resize_keyboard=True, is_persistent=True,
    )


def main_inline(lang: str) -> InlineKeyboardMarkup:
    return rows(
        [ib(t(lang, "btn_repos"), "repos:list:0"), ib(t(lang, "btn_new_repo"), "nr:start")],
        [ib(t(lang, "btn_upload"), "up:pick:0"), ib(t(lang, "btn_secrets"), "sec:pick:0")],
        [ib(t(lang, "btn_actions"), "act:pick:0"), ib(t(lang, "btn_ai"), "ai:home")],
        [ib(t(lang, "btn_scan"), "scan:run"), ib(t(lang, "btn_notifs"), "notif:list")],
        [ib(t(lang, "btn_settings"), "set:home"), ib(t(lang, "btn_help"), "help:home")],
    )


def back_menu(lang: str, back: str | None = None) -> InlineKeyboardMarkup:
    r = [ib(t(lang, "btn_menu"), "menu:home")]
    if back:
        r.insert(0, ib(t(lang, "btn_back"), back))
    return rows(r)


def cancel_kb(lang: str) -> InlineKeyboardMarkup:
    return rows([ib(t(lang, "btn_cancel"), "flow:cancel")])


def yes_no(lang: str, yes: str, no: str, yes_key: str = "btn_yes", no_key: str = "btn_no") -> InlineKeyboardMarkup:
    return rows([ib(t(lang, yes_key), yes), ib(t(lang, no_key), no)], [ib(t(lang, "btn_cancel"), "flow:cancel")])


def paginate(lang: str, items: list[tuple[str, str]], page: int, prefix: str, per_page: int = 8,
             extra: list[list[InlineKeyboardButton]] | None = None) -> tuple[InlineKeyboardMarkup, int]:
    pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, pages - 1))
    chunk = items[page * per_page:(page + 1) * per_page]
    kb = [[ib(text, data)] for text, data in chunk]
    nav = []
    if page > 0:
        nav.append(ib(t(lang, "btn_prev"), f"{prefix}:{page - 1}"))
    if page < pages - 1:
        nav.append(ib(t(lang, "btn_more"), f"{prefix}:{page + 1}"))
    if nav:
        kb.append(nav)
    for row in extra or []:
        kb.append(row)
    kb.append([ib(t(lang, "btn_menu"), "menu:home")])
    return InlineKeyboardMarkup(inline_keyboard=kb), pages


def repo_picker(lang: str, repos: list[dict], page: int, action: str) -> tuple[InlineKeyboardMarkup, int]:
    register_repos(repos)
    items = [((("🔒 " if r["private"] else "🌍 ") + r["full_name"])[:60], f"{action}:{rid(r['full_name'])}") for r in repos]
    return paginate(lang, items, page, f"{action.split(':')[0]}:pick")


def repo_card_kb(lang: str, full: str, watched: bool) -> InlineKeyboardMarkup:
    r = rid(full)
    return rows(
        [ib(t(lang, "btn_repo_upload"), f"up:repo:{r}"), ib(t(lang, "btn_repo_secrets"), f"sec:repo:{r}")],
        [ib(t(lang, "btn_repo_actions"), f"act:repo:{r}"), ib(t(lang, "btn_repo_files"), f"repos:files:{r}")],
        [ib(t(lang, "btn_repo_unwatch" if watched else "btn_repo_watch"), f"repos:{'unwatch' if watched else 'watch'}:{r}"),
         ib(t(lang, "btn_repo_settings"), f"repos:edit:{r}")],
        [ib(t(lang, "btn_repo_ai"), f"ai:repo:{r}"), ib(t(lang, "btn_repo_delete"), f"repos:del:{r}")],
        [ib(t(lang, "btn_back"), "repos:list:0"), ib(t(lang, "btn_menu"), "menu:home")],
    )


def ai_home_kb(lang: str) -> InlineKeyboardMarkup:
    return rows(
        [ib(t(lang, "btn_ai_new"), "ai:new"), ib(t(lang, "btn_ai_sessions"), "ai:sessions")],
        [ib(t(lang, "btn_ai_memory"), "ai:memory"), ib(t(lang, "btn_ai_skills"), "ai:skills")],
        [ib(t(lang, "btn_ai_model"), "ai:setup"), ib(t(lang, "btn_ai_stop"), "ai:stop")],
        [ib(t(lang, "btn_menu"), "menu:home")],
    )


def ai_stop_kb(lang: str) -> InlineKeyboardMarkup:
    return rows([ib(t(lang, "btn_ai_stop"), "ai:stop")])
