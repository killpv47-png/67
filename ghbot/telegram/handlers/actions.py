"""GitHub Actions: workflows, runs, dispatch, cancel, rerun, logs, running-now overview."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...github.client import GitHubError
from ...i18n import t
from ...lifecycle.handoff import RUN_ICON
from ..app import AppContext
from ..keyboards import back_menu, ib, repo_from_id, repo_picker, rid, rows
from ..states import ActionsFlow
from ..utils import age, edit_or_send, esc
from .router_bridge import entry

router = Router(name="actions")


def _icon(run: dict) -> str:
    return RUN_ICON.get(run.get("conclusion") or run.get("status") or "", "🔔")


async def pick_repo(event, app: AppContext, tg_id: int, lang: str, page: int, state: FSMContext):
    await state.clear()
    repos = await app.repos(tg_id)
    if not repos:
        await edit_or_send(event, t(lang, "repos_empty"), back_menu(lang))
        return
    kb, _ = repo_picker(lang, repos, page, "act:repo")
    kb.inline_keyboard.insert(-1, [ib(t(lang, "btn_act_running"), "act:running")])
    await edit_or_send(event, t(lang, "act_pick_repo"), kb)


@entry("act:pick:0")
async def entry_act(msg: Message, app: AppContext, lang: str, state: FSMContext):
    await pick_repo(msg, app, msg.from_user.id, lang, 0, state)


@router.message(Command("actions", "runs"))
async def cmd_actions(msg: Message, state: FSMContext, app: AppContext, lang: str):
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) == 2 and "/" in parts[1]:
        rid(parts[1].strip())
        await show_actions(msg, app, msg.from_user.id, lang, parts[1].strip())
    else:
        await pick_repo(msg, app, msg.from_user.id, lang, 0, state)


@router.callback_query(F.data.startswith("act:pick:"))
async def cb_pick(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    await pick_repo(cb, app, cb.from_user.id, lang, int(cb.data.split(":")[2]), state)


@router.callback_query(F.data.startswith("act:repo:"))
async def cb_repo(cb: CallbackQuery, app: AppContext, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    if full:
        await show_actions(cb, app, cb.from_user.id, lang, full)


async def show_actions(event, app: AppContext, tg_id: int, lang: str, full: str):
    gh = await app.gh(tg_id)
    if not gh:
        await edit_or_send(event, t(lang, "need_token"))
        return
    try:
        workflows = await gh.list_workflows(full)
        runs = await gh.list_runs(full, per_page=8)
    except GitHubError as e:
        await edit_or_send(event, t(lang, "error_generic", error=esc(e.message)), back_menu(lang, f"repos:card:{rid(full)}"))
        return
    finally:
        await gh.aclose()
    r = rid(full)
    wf_body = "\n".join(t(lang, "act_wf_item", name=esc(w["name"]), file=esc(w["path"].split("/")[-1]), state=w["state"]) for w in workflows) or t(lang, "act_none")
    run_body = "\n".join(t(lang, "act_run_item", icon=_icon(x), num=x["run_number"], name=esc(x.get("name", ""))[:30], status=x["status"],
                           conclusion=f"({x['conclusion']})" if x.get("conclusion") else "", branch=esc(x.get("head_branch", "")),
                           age=age(x.get("updated_at"))) for x in runs) or t(lang, "act_none")
    kb = rows(*[[ib(f"{_icon(x)} #{x['run_number']} {x.get('name', '')[:25]}", f"act:run:{r}:{x['id']}")] for x in runs[:6]],
              [ib(t(lang, "btn_act_dispatch"), f"act:dispatch:{r}"), ib(t(lang, "btn_refresh"), f"act:repo:{r}")],
              [ib(t(lang, "btn_back"), f"repos:card:{r}"), ib(t(lang, "btn_menu"), "menu:home")])
    await edit_or_send(event, t(lang, "act_title", full=esc(full), workflows=wf_body, runs=run_body)[:4000], kb)


@router.callback_query(F.data.startswith("act:run:"))
async def cb_run(cb: CallbackQuery, app: AppContext, lang: str):
    _, _, r, run_id = cb.data.split(":")
    full = repo_from_id(r)
    gh = await app.gh(cb.from_user.id)
    if not full or not gh:
        return
    try:
        run = await gh.get_run(full, int(run_id))
        jobs = await gh.run_jobs(full, int(run_id))
    except GitHubError as e:
        await edit_or_send(cb, t(lang, "error_generic", error=esc(e.message)), back_menu(lang, f"act:repo:{r}"))
        return
    finally:
        await gh.aclose()
    jobs_body = "\n".join(t(lang, "act_job_item", icon=_icon(j), name=esc(j["name"]), status=j["status"],
                            conclusion=f"({j['conclusion']})" if j.get("conclusion") else "") for j in jobs) or t(lang, "act_none")
    text = t(lang, "act_run_card", icon=_icon(run), num=run["run_number"], name=esc(run.get("name", "")), status=run["status"],
             conclusion=f"({run['conclusion']})" if run.get("conclusion") else "", branch=esc(run.get("head_branch", "")),
             event=run.get("event", ""), age=age(run.get("updated_at")), url=run["html_url"], jobs=jobs_body)
    row1 = []
    if run["status"] in ("in_progress", "queued", "waiting"):
        row1.append(ib(t(lang, "btn_run_cancel"), f"act:cancel:{r}:{run_id}"))
    else:
        row1.append(ib(t(lang, "btn_run_rerun"), f"act:rerun:{r}:{run_id}:0"))
        if run.get("conclusion") == "failure":
            row1.append(ib(t(lang, "btn_run_rerun_failed"), f"act:rerun:{r}:{run_id}:1"))
    row2 = [ib(t(lang, "btn_run_logs"), f"act:log:{r}:{jobs[-1]['id']}")] if jobs else []
    kb = rows(row1, row2, [ib(t(lang, "btn_refresh"), f"act:run:{r}:{run_id}"), ib(t(lang, "btn_back"), f"act:repo:{r}")])
    await edit_or_send(cb, text[:4000], kb)


@router.callback_query(F.data.startswith("act:cancel:"))
async def cb_cancel(cb: CallbackQuery, app: AppContext, lang: str):
    _, _, r, run_id = cb.data.split(":")
    full = repo_from_id(r)
    gh = await app.gh(cb.from_user.id)
    if not full or not gh:
        return
    try:
        await gh.cancel_run(full, int(run_id))
        run = await gh.get_run(full, int(run_id))
        await app.notifier.send(cb.from_user.id, t(lang, "act_cancelled", num=run["run_number"]), kind="actions")
    except GitHubError as e:
        await app.notifier.send(cb.from_user.id, t(lang, "error_generic", error=esc(e.message)), kind="error")
    finally:
        await gh.aclose()


@router.callback_query(F.data.startswith("act:rerun:"))
async def cb_rerun(cb: CallbackQuery, app: AppContext, lang: str):
    _, _, r, run_id, failed = cb.data.split(":")
    full = repo_from_id(r)
    gh = await app.gh(cb.from_user.id)
    if not full or not gh:
        return
    try:
        await gh.rerun(full, int(run_id), failed_only=failed == "1")
        run = await gh.get_run(full, int(run_id))
        await app.notifier.send(cb.from_user.id, t(lang, "act_rerun", num=run["run_number"]), kind="actions")
    except GitHubError as e:
        await app.notifier.send(cb.from_user.id, t(lang, "error_generic", error=esc(e.message)), kind="error")
    finally:
        await gh.aclose()


@router.callback_query(F.data.startswith("act:log:"))
async def cb_log(cb: CallbackQuery, app: AppContext, lang: str):
    _, _, r, job_id = cb.data.split(":")
    full = repo_from_id(r)
    gh = await app.gh(cb.from_user.id)
    if not full or not gh:
        return
    try:
        log_text = await gh.job_log(full, int(job_id), tail_chars=3000)
    except GitHubError as e:
        await edit_or_send(cb, t(lang, "error_generic", error=esc(e.message)), back_menu(lang, f"act:repo:{r}"))
        return
    finally:
        await gh.aclose()
    await edit_or_send(cb, t(lang, "act_logs", job=job_id, log=esc(log_text))[:4000], back_menu(lang, f"act:repo:{r}"))


@router.callback_query(F.data.startswith("act:dispatch:"))
async def cb_dispatch(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    r = cb.data.split(":")[2]
    full = repo_from_id(r)
    gh = await app.gh(cb.from_user.id)
    if not full or not gh:
        return
    try:
        workflows = [w for w in await gh.list_workflows(full) if w["state"] == "active"]
    finally:
        await gh.aclose()
    if not workflows:
        await edit_or_send(cb, t(lang, "act_none"), back_menu(lang, f"act:repo:{r}"))
        return
    kb = rows(*[[ib(f"▶️ {w['name']}", f"act:wf:{r}:{w['id']}")] for w in workflows[:12]], [ib(t(lang, "btn_back"), f"act:repo:{r}")])
    await edit_or_send(cb, t(lang, "act_pick_wf"), kb)


@router.callback_query(F.data.startswith("act:wf:"))
async def cb_wf(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    _, _, r, wf_id = cb.data.split(":")
    full = repo_from_id(r)
    gh = await app.gh(cb.from_user.id)
    branch = "main"
    if gh:
        try:
            branch = (await gh.get_repo(full))["default_branch"]
        finally:
            await gh.aclose()
    await state.set_state(ActionsFlow.ref)
    await state.update_data(repo=full, wf=int(wf_id), default_branch=branch)
    await edit_or_send(cb, t(lang, "act_pick_ref", branch=esc(branch)),
                       rows([ib(t(lang, "btn_use_default"), "act:ref:default")], [ib(t(lang, "btn_cancel"), "flow:cancel")]))


@router.callback_query(ActionsFlow.ref, F.data == "act:ref:default")
async def cb_ref_default(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    data = await state.get_data()
    await _dispatch(cb, state, app, lang, data["default_branch"])


@router.message(ActionsFlow.ref, F.text)
async def got_ref(msg: Message, state: FSMContext, app: AppContext, lang: str):
    await _dispatch(msg, state, app, lang, msg.text.strip())


async def _dispatch(event, state: FSMContext, app: AppContext, lang: str, ref: str):
    data = await state.get_data()
    await state.clear()
    tg_id = event.from_user.id
    gh = await app.gh(tg_id)
    if not gh:
        return
    try:
        await gh.dispatch_workflow(data["repo"], data["wf"], ref)
        wfs = {w["id"]: w["name"] for w in await gh.list_workflows(data["repo"])}
        await app.db.add_watch(tg_id, data["repo"])  # auto-watch so the user gets progress notifications
        await app.notifier.send(tg_id, t(lang, "act_dispatched", wf=esc(wfs.get(data["wf"], data["wf"])), ref=esc(ref)), kind="actions",
                                markup=back_menu(lang, f"act:repo:{rid(data['repo'])}"))
    except GitHubError as e:
        await app.notifier.send(tg_id, t(lang, "act_dispatch_fail", error=esc(e.message)), kind="error")
    finally:
        await gh.aclose()


@router.callback_query(F.data == "act:running")
async def cb_running(cb: CallbackQuery, app: AppContext, lang: str):
    gh = await app.gh(cb.from_user.id)
    if not gh:
        return
    try:
        repos = await app.repos(cb.from_user.id)
        running = await gh.scan_running_jobs(repos, limit=30)
    finally:
        await gh.aclose()
    if not running:
        await edit_or_send(cb, t(lang, "act_running_none"), back_menu(lang, "act:pick:0"))
        return
    body = "\n".join(t(lang, "scan_running_item", repo=esc(x["repo"]), name=esc(x.get("name", "")), status=x["status"]) for x in running[:20])
    kb = rows(*[[ib(f"🏃 {x['repo'].split('/')[1]} #{x['run_number']}", f"act:run:{rid(x['repo'])}:{x['id']}")] for x in running[:8]],
              [ib(t(lang, "btn_back"), "act:pick:0")])
    await edit_or_send(cb, t(lang, "act_running_global", list=body), kb)
