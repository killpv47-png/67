"""Actions secrets & variables: list / create / update / delete / detect-from-workflows."""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...github.client import GitHubError
from ...github.zipflow import detect_secrets_in_texts
from ...i18n import t
from ..app import AppContext
from ..keyboards import back_menu, cancel_kb, ib, repo_from_id, repo_picker, rid, rows
from ..states import SecretFlow
from ..utils import age, edit_or_send, esc, safe_delete
from .router_bridge import entry

router = Router(name="secrets")
NAME_RE = re.compile(r"^(?!GITHUB_)[A-Z_][A-Z0-9_]{0,99}$")


async def pick_repo(event, app: AppContext, tg_id: int, lang: str, page: int, state: FSMContext):
    await state.clear()
    repos = await app.repos(tg_id)
    if not repos:
        await edit_or_send(event, t(lang, "repos_empty"), back_menu(lang))
        return
    kb, _ = repo_picker(lang, repos, page, "sec:repo")
    await edit_or_send(event, t(lang, "sec_pick_repo"), kb)


@entry("sec:pick:0")
async def entry_sec(msg: Message, app: AppContext, lang: str, state: FSMContext):
    await pick_repo(msg, app, msg.from_user.id, lang, 0, state)


@router.message(Command("secrets"))
async def cmd_secrets(msg: Message, state: FSMContext, app: AppContext, lang: str):
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) == 2 and "/" in parts[1]:
        rid(parts[1].strip())
        await show_secrets(msg, app, msg.from_user.id, lang, parts[1].strip())
    else:
        await pick_repo(msg, app, msg.from_user.id, lang, 0, state)


@router.callback_query(F.data.startswith("sec:pick:"))
async def cb_pick(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    await pick_repo(cb, app, cb.from_user.id, lang, int(cb.data.split(":")[2]), state)


@router.callback_query(F.data.startswith("sec:repo:"))
async def cb_repo(cb: CallbackQuery, app: AppContext, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    if full:
        await show_secrets(cb, app, cb.from_user.id, lang, full)


async def show_secrets(event, app: AppContext, tg_id: int, lang: str, full: str):
    gh = await app.gh(tg_id)
    if not gh:
        await edit_or_send(event, t(lang, "need_token"))
        return
    try:
        secrets = await gh.list_secrets(full)
    except GitHubError as e:
        await edit_or_send(event, t(lang, "error_generic", error=esc(e.message)), back_menu(lang, f"repos:card:{rid(full)}"))
        return
    finally:
        await gh.aclose()
    r = rid(full)
    body = "\n".join(t(lang, "sec_item", name=esc(s["name"]), updated=age(s.get("updated_at"))) for s in secrets) or t(lang, "sec_none")
    kb = rows(*[[ib(f"🔐 {s['name']}", f"sec:one:{r}:{s['name']}")] for s in secrets[:20]],
              [ib(t(lang, "btn_sec_add"), f"sec:add:{r}"), ib(t(lang, "btn_sec_scan"), f"sec:scan:{r}")],
              [ib(t(lang, "btn_sec_vars"), f"sec:vars:{r}")],
              [ib(t(lang, "btn_back"), f"repos:card:{r}"), ib(t(lang, "btn_menu"), "menu:home")])
    await edit_or_send(event, t(lang, "sec_title", full=esc(full), n=len(secrets), list=body), kb)


@router.callback_query(F.data.startswith("sec:one:"))
async def cb_one(cb: CallbackQuery, lang: str):
    _, _, r, name = cb.data.split(":", 3)
    full = repo_from_id(r)
    kb = rows([ib(t(lang, "btn_sec_update"), f"sec:new:{r}:{name}"), ib(t(lang, "btn_sec_delete"), f"sec:del:{r}:{name}")],
              [ib(t(lang, "btn_back"), f"sec:repo:{r}")])
    await edit_or_send(cb, t(lang, "sec_actions", name=esc(name), full=esc(full)), kb)


@router.callback_query(F.data.startswith("sec:add:"))
async def cb_add(cb: CallbackQuery, state: FSMContext, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    await state.set_state(SecretFlow.name)
    await state.update_data(repo=full)
    await edit_or_send(cb, t(lang, "sec_ask_name"), cancel_kb(lang))


@router.message(SecretFlow.name, F.text)
async def got_name(msg: Message, state: FSMContext, lang: str):
    name = msg.text.strip().upper()
    if not NAME_RE.match(name):
        await msg.answer(t(lang, "sec_name_bad"), parse_mode="HTML")
        return
    await state.update_data(name=name)
    await state.set_state(SecretFlow.value)
    await msg.answer(t(lang, "sec_ask_value", name=esc(name)), parse_mode="HTML", reply_markup=cancel_kb(lang))


@router.callback_query(F.data.startswith("sec:new:"))
async def cb_new_named(cb: CallbackQuery, state: FSMContext, lang: str):
    _, _, r, name = cb.data.split(":", 3)
    await state.set_state(SecretFlow.value)
    await state.update_data(repo=repo_from_id(r), name=name)
    await edit_or_send(cb, t(lang, "sec_ask_value", name=esc(name)), cancel_kb(lang))


@router.message(SecretFlow.value, F.text)
async def got_value(msg: Message, state: FSMContext, app: AppContext, lang: str):
    value = msg.text
    await safe_delete(msg)
    data = await state.get_data()
    await state.clear()
    full, name = data["repo"], data["name"]
    gh = await app.gh(msg.from_user.id)
    if not gh:
        return
    try:
        await gh.set_secret(full, name, value)
        await app.notifier.send(msg.chat.id, t(lang, "sec_saved", name=esc(name), full=esc(full)), kind="secrets",
                                markup=back_menu(lang, f"sec:repo:{rid(full)}"))
    except GitHubError as e:
        await app.notifier.send(msg.chat.id, t(lang, "error_generic", error=esc(e.message)), kind="error")
    finally:
        await gh.aclose()


@router.callback_query(F.data.startswith("sec:del:"))
async def cb_del(cb: CallbackQuery, app: AppContext, lang: str):
    _, _, r, name = cb.data.split(":", 3)
    full = repo_from_id(r)
    gh = await app.gh(cb.from_user.id)
    if not full or not gh:
        return
    try:
        await gh.delete_secret(full, name)
        await app.notifier.send(cb.from_user.id, t(lang, "sec_deleted", name=esc(name)), kind="secrets")
    except GitHubError as e:
        await app.notifier.send(cb.from_user.id, t(lang, "error_generic", error=esc(e.message)), kind="error")
    finally:
        await gh.aclose()
    await show_secrets(cb, app, cb.from_user.id, lang, full)


@router.callback_query(F.data.startswith("sec:scan:"))
async def cb_scan(cb: CallbackQuery, app: AppContext, lang: str):
    r = cb.data.split(":")[2]
    full = repo_from_id(r)
    gh = await app.gh(cb.from_user.id)
    if not full or not gh:
        return
    try:
        repo = await gh.get_repo(full)
        tree = await gh.get_tree(full, repo["default_branch"])
        texts = {}
        for x in tree.get("tree", []):
            if x.get("type") == "blob" and x["path"].startswith(".github/workflows/") and x["path"].endswith((".yml", ".yaml")):
                txt = await gh.get_file_text(full, x["path"])
                if txt:
                    texts[x["path"]] = txt
        if not texts:
            await edit_or_send(cb, t(lang, "sec_detect_none"), back_menu(lang, f"sec:repo:{r}"))
            return
        needed = detect_secrets_in_texts(texts)
        existing = {s["name"] for s in await gh.list_secrets(full)}
    except GitHubError as e:
        await edit_or_send(cb, t(lang, "error_generic", error=esc(e.message)), back_menu(lang, f"sec:repo:{r}"))
        return
    finally:
        await gh.aclose()
    missing = [n for n in needed if n not in existing]
    kb = rows(*[[ib(f"🔐 {n}", f"sec:new:{r}:{n}")] for n in missing[:12]], [ib(t(lang, "btn_back"), f"sec:repo:{r}")])
    await edit_or_send(cb, t(lang, "sec_detect_result", all=", ".join(f"<code>{esc(n)}</code>" for n in needed) or "—",
                             missing=", ".join(esc(m) for m in missing) or "—"), kb)


# ------------------------------------------------------------- variables
@router.callback_query(F.data.startswith("sec:vars:"))
async def cb_vars(cb: CallbackQuery, app: AppContext, lang: str):
    r = cb.data.split(":")[2]
    full = repo_from_id(r)
    gh = await app.gh(cb.from_user.id)
    if not full or not gh:
        return
    try:
        variables = await gh.list_variables(full)
    finally:
        await gh.aclose()
    body = "\n".join(t(lang, "vars_item", name=esc(v["name"]), value=esc(v.get("value", ""))[:60]) for v in variables) or t(lang, "none")
    kb = rows([ib(t(lang, "btn_var_add"), f"sec:varadd:{r}")], [ib(t(lang, "btn_back"), f"sec:repo:{r}")])
    await edit_or_send(cb, t(lang, "vars_title", full=esc(full), list=body), kb)


@router.callback_query(F.data.startswith("sec:varadd:"))
async def cb_varadd(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.set_state(SecretFlow.var_name)
    await state.update_data(repo=repo_from_id(cb.data.split(":")[2]))
    await edit_or_send(cb, t(lang, "var_ask_name"), cancel_kb(lang))


@router.message(SecretFlow.var_name, F.text)
async def got_var_name(msg: Message, state: FSMContext, lang: str):
    name = msg.text.strip().upper()
    if not NAME_RE.match(name):
        await msg.answer(t(lang, "sec_name_bad"), parse_mode="HTML")
        return
    await state.update_data(name=name)
    await state.set_state(SecretFlow.var_value)
    await msg.answer(t(lang, "var_ask_value", name=esc(name)), parse_mode="HTML", reply_markup=cancel_kb(lang))


@router.message(SecretFlow.var_value, F.text)
async def got_var_value(msg: Message, state: FSMContext, app: AppContext, lang: str):
    data = await state.get_data()
    await state.clear()
    gh = await app.gh(msg.from_user.id)
    if not gh:
        return
    try:
        await gh.set_variable(data["repo"], data["name"], msg.text.strip())
        await app.notifier.send(msg.chat.id, t(lang, "var_saved", name=esc(data["name"])), kind="secrets",
                                markup=back_menu(lang, f"sec:vars:{rid(data['repo'])}"))
    except GitHubError as e:
        await app.notifier.send(msg.chat.id, t(lang, "error_generic", error=esc(e.message)), kind="error")
    finally:
        await gh.aclose()
