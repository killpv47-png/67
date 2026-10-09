"""Upload ZIP to a repository — the full step-by-step flow the user specified."""

from __future__ import annotations

import io
import secrets as _secrets

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...github.client import GitHubError
from ...github.zipflow import ZipError, ZipInfo, analyze_zip, strip_root
from ...i18n import t
from ..app import AppContext
from ..keyboards import back_menu, cancel_kb, ib, repo_from_id, repo_picker, rid, rows
from ..states import Upload
from ..utils import edit_or_send, esc, human_size
from .router_bridge import entry

router = Router(name="upload")
_ZIPS: dict[int, ZipInfo] = {}  # tg_id -> analyzed zip (kept in memory for the flow only)


async def pick_repo(event, app: AppContext, tg_id: int, lang: str, page: int, state: FSMContext):
    await state.clear()
    repos = await app.repos(tg_id)
    if not repos:
        await edit_or_send(event, t(lang, "repos_empty"), back_menu(lang))
        return
    kb, _ = repo_picker(lang, repos, page, "up:repo")
    await edit_or_send(event, t(lang, "up_pick_repo"), kb)


@entry("up:pick:0")
async def entry_up(msg: Message, app: AppContext, lang: str, state: FSMContext):
    await pick_repo(msg, app, msg.from_user.id, lang, 0, state)


@router.message(Command("upload"))
async def cmd_upload(msg: Message, state: FSMContext, app: AppContext, lang: str):
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) == 2 and "/" in parts[1]:
        await _ask_zip(msg, state, lang, parts[1].strip())
    else:
        await pick_repo(msg, app, msg.from_user.id, lang, 0, state)


@router.callback_query(F.data.startswith("up:pick:"))
async def cb_pick(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    await pick_repo(cb, app, cb.from_user.id, lang, int(cb.data.split(":")[2]), state)


@router.callback_query(F.data.startswith("up:repo:"))
async def cb_repo(cb: CallbackQuery, state: FSMContext, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    if full:
        await _ask_zip(cb, state, lang, full)


async def _ask_zip(event, state: FSMContext, lang: str, full: str):
    await state.set_state(Upload.zip)
    await state.update_data(repo=full)
    await edit_or_send(event, t(lang, "up_send_zip", full=esc(full)), cancel_kb(lang))


@router.message(Upload.zip, F.document)
async def got_zip(msg: Message, state: FSMContext, app: AppContext, lang: str):
    doc = msg.document
    if not (doc.file_name or "").lower().endswith(".zip") and doc.mime_type not in ("application/zip", "application/x-zip-compressed"):
        await msg.answer(t(lang, "up_not_zip"), parse_mode="HTML")
        return
    data = await state.get_data()
    full = data["repo"]
    job_id = _secrets.token_hex(4)
    await app.db.create_job(job_id, msg.from_user.id, "upload", f"Upload {doc.file_name} → {full}")
    await state.update_data(job_id=job_id)
    status = await msg.answer(t(lang, "up_downloading"), parse_mode="HTML")
    buf = io.BytesIO()
    try:
        await app.bot.download(doc, destination=buf)
    except Exception as e:
        await app.db.finish_job(job_id, "failed")
        await status.edit_text(t(lang, "up_fail", error=esc(str(e)[:200])), parse_mode="HTML")
        return
    await app.notifier.step(msg.chat.id, f"ZIP downloaded ({human_size(buf.tell())})", job_id=job_id)
    await status.edit_text(t(lang, "up_analyzing"), parse_mode="HTML")
    try:
        zi = analyze_zip(buf.getvalue())
    except ZipError as e:
        await app.db.finish_job(job_id, "failed")
        await status.edit_text(t(lang, "up_bad_zip", error=esc(str(e))), parse_mode="HTML")
        return
    _ZIPS[msg.from_user.id] = zi
    skipped = t(lang, "up_skipped", n=len(zi.skipped)) if zi.skipped else ""
    await status.edit_text(
        t(lang, "up_analysis", count=zi.count, size=human_size(zi.total_bytes),
          workflows=", ".join(esc(w) for w in zi.workflows) or "—",
          secrets=", ".join(f"<code>{esc(s)}</code>" for s in zi.secrets) or "—", skipped=skipped),
        parse_mode="HTML")
    await app.notifier.step(msg.chat.id, f"Analyzed: {zi.count} files, {len(zi.workflows)} workflows, {len(zi.secrets)} secrets referenced", job_id=job_id)
    await state.set_state(Upload.wipe)
    await msg.answer(t(lang, "up_wipe_q", full=esc(full)), parse_mode="HTML",
                     reply_markup=rows([ib(t(lang, "btn_wipe_yes"), "up:wipe:1")], [ib(t(lang, "btn_wipe_no"), "up:wipe:0")],
                                       [ib(t(lang, "btn_cancel"), "flow:cancel")]))


@router.message(Upload.zip)
async def not_zip(msg: Message, lang: str):
    await msg.answer(t(lang, "up_not_zip"), parse_mode="HTML")


@router.callback_query(Upload.wipe, F.data.startswith("up:wipe:"))
async def cb_wipe(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    wipe = cb.data.endswith("1")
    await state.update_data(wipe=wipe)
    zi = _ZIPS.get(cb.from_user.id)
    if not zi:
        await state.clear()
        return
    if zi.single_root:
        await state.set_state(Upload.root)
        await edit_or_send(cb, t(lang, "up_root_q", root=esc(zi.single_root)),
                           rows([ib(t(lang, "btn_root_keep"), "up:root:keep"), ib(t(lang, "btn_root_strip"), "up:root:strip")],
                                [ib(t(lang, "btn_cancel"), "flow:cancel")]))
    else:
        await _ask_branch(cb, state, app, lang)


@router.callback_query(Upload.root, F.data.startswith("up:root:"))
async def cb_root(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    if cb.data.endswith("strip"):
        _ZIPS[cb.from_user.id] = strip_root(_ZIPS[cb.from_user.id])
    await _ask_branch(cb, state, app, lang)


async def _ask_branch(event, state: FSMContext, app: AppContext, lang: str):
    data = await state.get_data()
    tg_id = event.from_user.id
    gh = await app.gh(tg_id)
    branch = "main"
    if gh:
        try:
            branch = (await gh.get_repo(data["repo"]))["default_branch"]
        except GitHubError:
            pass
        finally:
            await gh.aclose()
    await state.update_data(default_branch=branch)
    await state.set_state(Upload.branch)
    await edit_or_send(event, t(lang, "up_branch_q", branch=esc(branch)),
                       rows([ib(t(lang, "btn_use_default"), "up:branch:default")], [ib(t(lang, "btn_cancel"), "flow:cancel")]))


@router.callback_query(Upload.branch, F.data == "up:branch:default")
async def cb_branch_default(cb: CallbackQuery, state: FSMContext, lang: str):
    data = await state.get_data()
    await state.update_data(branch=data["default_branch"])
    await _ask_message(cb, state, lang)


@router.message(Upload.branch, F.text)
async def got_branch(msg: Message, state: FSMContext, lang: str):
    await state.update_data(branch=msg.text.strip())
    await _ask_message(msg, state, lang)


async def _ask_message(event, state: FSMContext, lang: str):
    await state.set_state(Upload.message)
    await edit_or_send(event, t(lang, "up_commit_q"),
                       rows([ib(t(lang, "btn_default_msg"), "up:msg:default")], [ib(t(lang, "btn_cancel"), "flow:cancel")]))


@router.callback_query(Upload.message, F.data == "up:msg:default")
async def cb_msg_default(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    await _do_upload(cb, state, app, lang, None)


@router.message(Upload.message, F.text)
async def got_msg(msg: Message, state: FSMContext, app: AppContext, lang: str):
    await _do_upload(msg, state, app, lang, msg.text.strip())


async def _do_upload(event, state: FSMContext, app: AppContext, lang: str, message: str | None):
    data = await state.get_data()
    await state.clear()
    tg_id = event.from_user.id
    chat_id = event.message.chat.id if isinstance(event, CallbackQuery) else event.chat.id
    zi = _ZIPS.pop(tg_id, None)
    if not zi:
        return
    full, branch, job_id = data["repo"], data.get("branch") or data.get("default_branch", "main"), data.get("job_id")
    wipe = bool(data.get("wipe"))
    message = message or f"Upload {zi.count} files via GitHub Control Bot" + (" (replace all)" if wipe else "")
    status = await edit_or_send(event, t(lang, "up_starting", count=zi.count, full=esc(full), branch=esc(branch)))

    async def progress(m: str):
        if status:
            await app.notifier.edit(chat_id, status.message_id, t(lang, "up_progress", msg=esc(m)))

    gh = await app.gh(tg_id)
    if not gh:
        return
    try:
        commit = await gh.commit_tree(full, branch, zi.files, message, replace_all=wipe, progress=progress)
    except GitHubError as e:
        await app.db.finish_job(job_id, "failed")
        await app.notifier.step(chat_id, t(lang, "up_fail", error=esc(e.message)), job_id=job_id, ok=False)
        await gh.aclose()
        return
    await app.db.finish_job(job_id, "done")
    url = commit.get("html_url") or f"https://github.com/{full}/commit/{commit['sha']}"
    await app.notifier.step(chat_id, t(lang, "up_done", sha=commit["sha"][:10], url=url), job_id=job_id)

    # Secrets offer
    if zi.secrets:
        try:
            existing = {s["name"] for s in await gh.list_secrets(full)}
        except GitHubError:
            existing = set()
        missing = [s for s in zi.secrets if s not in existing]
        if missing:
            r = rid(full)
            kb = rows(*[[ib(f"🔐 {s}", f"sec:new:{r}:{s}")] for s in missing[:12]], [ib(t(lang, "btn_menu"), "menu:home")])
            await app.notifier.send(chat_id, t(lang, "up_secrets_offer", list="\n".join(f"• <code>{esc(s)}</code>" for s in zi.secrets),
                                               missing=", ".join(esc(m) for m in missing)), kind="secrets", markup=kb)
        else:
            await app.notifier.send(chat_id, t(lang, "up_secrets_all_present"), kind="secrets")
    await gh.aclose()
