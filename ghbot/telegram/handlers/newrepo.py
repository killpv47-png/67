"""New repository wizard — every option GitHub's create API supports."""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...github.client import GitHubError
from ...i18n import t
from ..app import AppContext
from ..keyboards import cancel_kb, ib, rid, rows
from ..states import NewRepo
from ..utils import edit_or_send, esc
from .router_bridge import entry

router = Router(name="newrepo")
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
GITIGNORES = ["Python", "Node", "Go", "Rust", "Java", "C++", "Unity", "Android", "Swift", "Dart", "Ruby", "PHP"]
LICENSES = [("MIT", "mit"), ("Apache 2.0", "apache-2.0"), ("GPL v3", "gpl-3.0"), ("BSD 3", "bsd-3-clause"),
            ("MPL 2.0", "mpl-2.0"), ("Unlicense", "unlicense")]


async def start(event, app: AppContext, lang: str, state: FSMContext):
    await state.clear()
    await state.set_state(NewRepo.name)
    await state.update_data(private=True, auto_init=True, has_issues=True, has_wiki=False, has_projects=False,
                            is_template=False, description="", gitignore=None, license=None)
    await edit_or_send(event, t(lang, "nr_name"), cancel_kb(lang))


@entry("nr:start")
async def entry_nr(msg: Message, app: AppContext, lang: str, state: FSMContext):
    await start(msg, app, lang, state)


@router.message(Command("newrepo", "new"))
async def cmd_new(msg: Message, state: FSMContext, app: AppContext, lang: str):
    await start(msg, app, lang, state)


@router.callback_query(F.data == "nr:start")
async def cb_start(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    await start(cb, app, lang, state)


@router.message(NewRepo.name, F.text)
async def got_name(msg: Message, state: FSMContext, app: AppContext, lang: str):
    name = msg.text.strip()
    if not NAME_RE.match(name):
        await msg.answer(t(lang, "nr_name_bad"), parse_mode="HTML")
        return
    await state.update_data(name=name)
    gh = await app.gh(msg.from_user.id)
    orgs, login = [], ""
    if gh:
        try:
            login = (await gh.me())["login"]
            orgs = [o["login"] for o in await gh.list_orgs()]
        except GitHubError:
            pass
        finally:
            await gh.aclose()
    await state.update_data(login=login)
    if not orgs:
        await state.update_data(org=None)
        await state.set_state(NewRepo.desc)
        await msg.answer(t(lang, "nr_desc"), reply_markup=cancel_kb(lang), parse_mode="HTML")
        return
    await state.set_state(NewRepo.owner)
    kb = rows([ib(f"👤 {login}", "nr:owner:")], *[[ib(f"🏢 {o}", f"nr:owner:{o}")] for o in orgs[:10]],
              [ib(t(lang, "btn_cancel"), "flow:cancel")])
    await msg.answer(t(lang, "nr_owner"), reply_markup=kb, parse_mode="HTML")


@router.callback_query(NewRepo.owner, F.data.startswith("nr:owner:"))
async def cb_owner(cb: CallbackQuery, state: FSMContext, lang: str):
    org = cb.data.split(":", 2)[2] or None
    await state.update_data(org=org)
    await state.set_state(NewRepo.desc)
    await edit_or_send(cb, t(lang, "nr_desc"), cancel_kb(lang))


@router.message(NewRepo.desc, Command("skip"))
async def skip_desc(msg: Message, state: FSMContext, lang: str):
    await _ask_vis(msg, state, lang)


@router.message(NewRepo.desc, F.text)
async def got_desc(msg: Message, state: FSMContext, lang: str):
    await state.update_data(description=msg.text.strip()[:350])
    await _ask_vis(msg, state, lang)


async def _ask_vis(event, state: FSMContext, lang: str):
    await state.set_state(NewRepo.vis)
    kb = rows([ib(t(lang, "btn_private"), "nr:vis:1"), ib(t(lang, "btn_public"), "nr:vis:0")],
              [ib(t(lang, "btn_cancel"), "flow:cancel")])
    await edit_or_send(event, t(lang, "nr_vis"), kb)


@router.callback_query(NewRepo.vis, F.data.startswith("nr:vis:"))
async def cb_vis(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.update_data(private=cb.data.endswith("1"))
    await state.set_state(NewRepo.readme)
    kb = rows([ib(t(lang, "btn_yes"), "nr:readme:1"), ib(t(lang, "btn_no"), "nr:readme:0")],
              [ib(t(lang, "btn_cancel"), "flow:cancel")])
    await edit_or_send(cb, t(lang, "nr_readme"), kb)


@router.callback_query(NewRepo.readme, F.data.startswith("nr:readme:"))
async def cb_readme(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.update_data(auto_init=cb.data.endswith("1"))
    await state.set_state(NewRepo.gitignore)
    kb = rows(*[[ib(g, f"nr:gi:{g}") for g in GITIGNORES[i:i + 3]] for i in range(0, len(GITIGNORES), 3)],
              [ib(t(lang, "btn_skip"), "nr:gi:"), ib(t(lang, "btn_cancel"), "flow:cancel")])
    await edit_or_send(cb, t(lang, "nr_gitignore"), kb)


@router.callback_query(NewRepo.gitignore, F.data.startswith("nr:gi:"))
async def cb_gi(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.update_data(gitignore=cb.data.split(":", 2)[2] or None)
    await state.set_state(NewRepo.license)
    kb = rows(*[[ib(n, f"nr:lic:{k}") for n, k in LICENSES[i:i + 2]] for i in range(0, len(LICENSES), 2)],
              [ib(t(lang, "btn_skip"), "nr:lic:"), ib(t(lang, "btn_cancel"), "flow:cancel")])
    await edit_or_send(cb, t(lang, "nr_license"), kb)


@router.callback_query(NewRepo.license, F.data.startswith("nr:lic:"))
async def cb_lic(cb: CallbackQuery, state: FSMContext, lang: str):
    await state.update_data(license=cb.data.split(":", 2)[2] or None)
    await state.set_state(NewRepo.features)
    await _show_summary(cb, state, lang)


def _features_kb(lang: str, d: dict):
    def on(k, key):
        return ib(t(lang, f"btn_{key}_{'on' if d.get(k) else 'off'}"), f"nr:f:{k}")
    return rows(
        [on("has_issues", "issues"), on("has_wiki", "wiki")],
        [on("has_projects", "projects"), on("is_template", "template")],
        [ib(t(lang, "btn_create"), "nr:create"), ib(t(lang, "btn_cancel"), "flow:cancel")],
    )


async def _show_summary(event, state: FSMContext, lang: str):
    d = await state.get_data()

    def yn(v):
        return t(lang, "yes" if v else "no")
    text = t(lang, "nr_summary", owner=esc(d.get("org") or d.get("login") or "me"), name=esc(d["name"]),
             vis=t(lang, "private" if d["private"] else "public"), readme=yn(d["auto_init"]),
             gitignore=d.get("gitignore") or "—", license=d.get("license") or "—",
             desc=esc(d.get("description") or "—"), issues=yn(d["has_issues"]), wiki=yn(d["has_wiki"]),
             projects=yn(d["has_projects"]), template=yn(d["is_template"]))
    await edit_or_send(event, text + "\n\n" + t(lang, "nr_features"), _features_kb(lang, d))


@router.callback_query(NewRepo.features, F.data.startswith("nr:f:"))
async def cb_feature(cb: CallbackQuery, state: FSMContext, lang: str):
    k = cb.data.split(":")[2]
    d = await state.get_data()
    await state.update_data(**{k: not d.get(k)})
    await _show_summary(cb, state, lang)


@router.callback_query(NewRepo.features, F.data == "nr:create")
async def cb_create(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    d = await state.get_data()
    await state.clear()
    await edit_or_send(cb, t(lang, "nr_creating"))
    gh = await app.gh(cb.from_user.id)
    if not gh:
        return
    try:
        r = await gh.create_repo(name=d["name"], private=d["private"], description=d.get("description", ""),
                                 auto_init=d["auto_init"], gitignore_template=d.get("gitignore"),
                                 license_template=d.get("license"), has_issues=d["has_issues"], has_wiki=d["has_wiki"],
                                 has_projects=d["has_projects"], org=d.get("org"), is_template=d["is_template"])
    except GitHubError as e:
        await app.notifier.send(cb.from_user.id, t(lang, "nr_fail", error=esc(e.message)), kind="error")
        return
    finally:
        await gh.aclose()
    app.repo_cache.pop(cb.from_user.id, None)
    full = r["full_name"]
    kb = rows([ib(t(lang, "btn_repo_upload"), f"up:repo:{rid(full)}"), ib(t(lang, "btn_repo_secrets"), f"sec:repo:{rid(full)}")],
              [ib(t(lang, "btn_menu"), "menu:home")])
    await app.notifier.send(cb.from_user.id, t(lang, "nr_done", url=r["html_url"]), kind="repo", markup=kb)
