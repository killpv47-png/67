"""Repositories: list, card, file tree, watch/unwatch, edit, delete."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...github.client import GitHubError
from ...i18n import t
from ..app import AppContext
from ..keyboards import back_menu, cancel_kb, ib, repo_card_kb, repo_from_id, repo_picker, rid, rows
from ..states import RepoEdit
from ..utils import age, edit_or_send, esc
from .router_bridge import entry

router = Router(name="repos")


async def list_repos(event, app: AppContext, tg_id: int, lang: str, page: int, refresh: bool = False):
    repos = await app.repos(tg_id, refresh=refresh)
    if not repos:
        await edit_or_send(event, t(lang, "repos_empty"), back_menu(lang))
        return
    kb, pages = repo_picker(lang, repos, page, "repos:card")
    await edit_or_send(event, t(lang, "repos_title", page=page + 1, pages=pages), kb)


@entry("repos:list:0")
async def entry_repos(msg: Message, app: AppContext, lang: str, state: FSMContext):
    await list_repos(msg, app, msg.from_user.id, lang, 0)


@router.message(Command("repos"))
async def cmd_repos(msg: Message, app: AppContext, lang: str):
    await list_repos(msg, app, msg.from_user.id, lang, 0, refresh=True)


@router.callback_query(F.data.startswith("repos:list:"))
async def cb_list(cb: CallbackQuery, app: AppContext, lang: str):
    await list_repos(cb, app, cb.from_user.id, lang, int(cb.data.split(":")[2]))


@router.callback_query(F.data.startswith("repos:pick:"))
async def cb_page(cb: CallbackQuery, app: AppContext, lang: str):
    await list_repos(cb, app, cb.from_user.id, lang, int(cb.data.split(":")[2]))


async def show_card(event, app: AppContext, tg_id: int, lang: str, full: str):
    gh = await app.gh(tg_id)
    if not gh:
        await edit_or_send(event, t(lang, "need_token"))
        return
    try:
        r = await gh.get_repo(full)
    except GitHubError as e:
        await edit_or_send(event, t(lang, "error_generic", error=esc(e.message)), back_menu(lang, "repos:list:0"))
        return
    finally:
        await gh.aclose()
    watched = any(w["repo"] == full for w in await app.db.list_watches(tg_id))
    text = t(lang, "repo_card", full=esc(r["full_name"]), vis=t(lang, "private" if r["private"] else "public"),
             desc=esc(r.get("description") or "—"), stars=r.get("stargazers_count", 0), forks=r.get("forks_count", 0),
             issues=r.get("open_issues_count", 0), branch=esc(r.get("default_branch", "")), updated=age(r.get("updated_at")),
             url=r["html_url"])
    await edit_or_send(event, text, repo_card_kb(lang, full, watched))


@router.callback_query(F.data.startswith("repos:card:"))
async def cb_card(cb: CallbackQuery, app: AppContext, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    if full:
        await show_card(cb, app, cb.from_user.id, lang, full)


@router.message(Command("repo"))
async def cmd_repo(msg: Message, app: AppContext, lang: str):
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2 or "/" not in parts[1]:
        await msg.answer("Usage: /repo owner/name")
        return
    rid(parts[1].strip())
    await show_card(msg, app, msg.from_user.id, lang, parts[1].strip())


@router.callback_query(F.data.startswith("repos:files:"))
async def cb_files(cb: CallbackQuery, app: AppContext, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    gh = await app.gh(cb.from_user.id)
    if not full or not gh:
        return
    try:
        r = await gh.get_repo(full)
        tree = await gh.get_tree(full, r["default_branch"])
    except GitHubError as e:
        await edit_or_send(cb, t(lang, "error_generic", error=esc(e.message)), back_menu(lang, f"repos:card:{rid(full)}"))
        return
    finally:
        await gh.aclose()
    paths = [x["path"] for x in tree.get("tree", []) if x.get("type") == "blob"]
    shown = "\n".join(esc(p) for p in paths[:120])
    if len(paths) > 120:
        shown += f"\n… +{len(paths) - 120}"
    await edit_or_send(cb, t(lang, "repo_files_title", full=esc(full), ref=esc(r["default_branch"]), count=len(paths), tree=shown)[:4000],
                       back_menu(lang, f"repos:card:{rid(full)}"))


@router.callback_query(F.data.startswith("repos:watch:"))
async def cb_watch(cb: CallbackQuery, app: AppContext, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    if not full:
        return
    await app.db.add_watch(cb.from_user.id, full)
    await app.notifier.send(cb.from_user.id, t(lang, "watch_on", full=esc(full)), kind="watch")
    await show_card(cb, app, cb.from_user.id, lang, full)


@router.callback_query(F.data.startswith("repos:unwatch:"))
async def cb_unwatch(cb: CallbackQuery, app: AppContext, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    if not full:
        return
    await app.db.remove_watch(cb.from_user.id, full)
    await app.notifier.send(cb.from_user.id, t(lang, "watch_off", full=esc(full)), kind="watch")
    await show_card(cb, app, cb.from_user.id, lang, full)


# ------------------------------------------------------------------ edit
def _edit_kb(lang: str, full: str):
    r = rid(full)
    return rows(
        [ib(t(lang, "btn_toggle_private"), f"repos:tgl:private:{r}"), ib(t(lang, "btn_edit_desc"), f"repos:desc:{r}")],
        [ib(t(lang, "btn_toggle_issues"), f"repos:tgl:has_issues:{r}"), ib(t(lang, "btn_toggle_wiki"), f"repos:tgl:has_wiki:{r}")],
        [ib(t(lang, "btn_default_branch"), f"repos:branch:{r}")],
        [ib(t(lang, "btn_back"), f"repos:card:{r}"), ib(t(lang, "btn_menu"), "menu:home")],
    )


@router.callback_query(F.data.startswith("repos:edit:"))
async def cb_edit(cb: CallbackQuery, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    if full:
        await edit_or_send(cb, t(lang, "repo_edit_title", full=esc(full)), _edit_kb(lang, full))


@router.callback_query(F.data.startswith("repos:tgl:"))
async def cb_toggle(cb: CallbackQuery, app: AppContext, lang: str):
    _, _, field, r = cb.data.split(":")
    full = repo_from_id(r)
    gh = await app.gh(cb.from_user.id)
    if not full or not gh:
        return
    try:
        repo = await gh.get_repo(full)
        await gh.update_repo(full, **{field: not repo.get(field)})
        await app.notifier.send(cb.from_user.id, t(lang, "repo_updated") + f" ({field} → {not repo.get(field)})", kind="repo")
    except GitHubError as e:
        await app.notifier.send(cb.from_user.id, t(lang, "error_generic", error=esc(e.message)), kind="error")
    finally:
        await gh.aclose()
    await edit_or_send(cb, t(lang, "repo_edit_title", full=esc(full)), _edit_kb(lang, full))


@router.callback_query(F.data.startswith("repos:desc:"))
async def cb_desc(cb: CallbackQuery, state: FSMContext, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    await state.set_state(RepoEdit.desc)
    await state.update_data(repo=full)
    await edit_or_send(cb, t(lang, "ask_description"), cancel_kb(lang))


@router.message(RepoEdit.desc, F.text)
async def got_desc(msg: Message, state: FSMContext, app: AppContext, lang: str):
    data = await state.get_data()
    await state.clear()
    await _update(msg, app, lang, data["repo"], description=msg.text.strip()[:350])


@router.callback_query(F.data.startswith("repos:branch:"))
async def cb_branch(cb: CallbackQuery, state: FSMContext, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    await state.set_state(RepoEdit.branch)
    await state.update_data(repo=full)
    await edit_or_send(cb, t(lang, "ask_default_branch"), cancel_kb(lang))


@router.message(RepoEdit.branch, F.text)
async def got_branch(msg: Message, state: FSMContext, app: AppContext, lang: str):
    data = await state.get_data()
    await state.clear()
    await _update(msg, app, lang, data["repo"], default_branch=msg.text.strip())


async def _update(msg: Message, app: AppContext, lang: str, full: str, **fields):
    gh = await app.gh(msg.from_user.id)
    if not gh:
        return
    try:
        await gh.update_repo(full, **fields)
        await msg.answer(t(lang, "repo_updated"), reply_markup=_edit_kb(lang, full))
    except GitHubError as e:
        await msg.answer(t(lang, "error_generic", error=esc(e.message)), parse_mode="HTML", reply_markup=_edit_kb(lang, full))
    finally:
        await gh.aclose()


# ---------------------------------------------------------------- delete
@router.callback_query(F.data.startswith("repos:del:"))
async def cb_delete(cb: CallbackQuery, state: FSMContext, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    if not full:
        return
    await state.set_state(RepoEdit.delete_confirm)
    await state.update_data(repo=full)
    await edit_or_send(cb, t(lang, "repo_delete_confirm", full=esc(full), name=esc(full.split("/")[1])), cancel_kb(lang))


@router.message(RepoEdit.delete_confirm, F.text)
async def got_delete(msg: Message, state: FSMContext, app: AppContext, lang: str):
    data = await state.get_data()
    await state.clear()
    full = data["repo"]
    if msg.text.strip() != full.split("/")[1]:
        await msg.answer(t(lang, "repo_delete_mismatch"), parse_mode="HTML")
        return
    gh = await app.gh(msg.from_user.id)
    if not gh:
        return
    try:
        await gh.delete_repo(full)
        app.repo_cache.pop(msg.from_user.id, None)
        await app.db.remove_watch(msg.from_user.id, full)
        await app.notifier.send(msg.from_user.id, t(lang, "repo_deleted", full=esc(full)), kind="repo")
    except GitHubError as e:
        await msg.answer(t(lang, "error_generic", error=esc(e.message)), parse_mode="HTML")
    finally:
        await gh.aclose()
