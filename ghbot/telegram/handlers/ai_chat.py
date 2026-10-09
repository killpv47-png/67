"""GITHUB_AI Telegram surface: setup wizard, chat, live step notifications, sessions/memory/skills, stop, resume."""

from __future__ import annotations

import asyncio
import json
import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...ai.agent import Agent, AgentConfig, RunResult
from ...ai.llm import LLMClient, LLMError
from ...ai.memory import MemoryStore
from ...ai.skills import catalog
from ...github.access import LEVELS
from ...i18n import t
from ..app import AppContext
from ..keyboards import ai_home_kb, ai_stop_kb, back_menu, cancel_kb, ib, paginate, repo_from_id, rows
from ..states import AISetup
from ..utils import edit_or_send, esc, safe_delete
from .menu import BUTTONS
from .router_bridge import entry

router = Router(name="ai")
log = logging.getLogger(__name__)
_MODELS: dict[int, list[str]] = {}


# ------------------------------------------------------------------ setup
async def setup_start(event, state: FSMContext, lang: str):
    await state.clear()
    await state.set_state(AISetup.base)
    await edit_or_send(event, t(lang, "ai_setup_base"), cancel_kb(lang))


@router.callback_query(F.data == "ai:setup")
async def cb_setup(cb: CallbackQuery, state: FSMContext, lang: str):
    await setup_start(cb, state, lang)


@router.message(Command("ai_setup"))
async def cmd_setup(msg: Message, state: FSMContext, lang: str):
    await setup_start(msg, state, lang)


@router.message(AISetup.base, F.text)
async def got_base(msg: Message, state: FSMContext, lang: str):
    base = msg.text.strip().rstrip("/")
    if not re.match(r"^https?://", base):
        base = "https://" + base
    await state.update_data(base=base)
    await state.set_state(AISetup.key)
    await msg.answer(t(lang, "ai_setup_key"), parse_mode="HTML", reply_markup=cancel_kb(lang))


@router.message(AISetup.key, F.text)
async def got_key(msg: Message, state: FSMContext, app: AppContext, lang: str):
    key = msg.text.strip()
    await safe_delete(msg)
    data = await state.get_data()
    base = data["base"]
    await state.update_data(key=key)
    status = await msg.answer(t(lang, "ai_fetching_models", base=esc(base)), parse_mode="HTML")
    client = LLMClient(base, key)
    try:
        models = await client.list_models()
    except (LLMError, Exception) as e:
        await status.edit_text(t(lang, "ai_models_fail", error=esc(str(e)[:200])), parse_mode="HTML", reply_markup=cancel_kb(lang))
        await state.set_state(AISetup.model)
        return
    finally:
        await client.aclose()
    if not models:
        await status.edit_text(t(lang, "ai_models_fail", error="empty list"), parse_mode="HTML", reply_markup=cancel_kb(lang))
        await state.set_state(AISetup.model)
        return
    _MODELS[msg.from_user.id] = models
    await state.set_state(AISetup.model)
    await _show_models(status, msg.from_user.id, lang, 0, edit=True)


async def _show_models(msg: Message, tg_id: int, lang: str, page: int, edit: bool = False):
    models = _MODELS.get(tg_id, [])
    items = [(m[:60], f"ai:model:{i}") for i, m in enumerate(models)]
    kb, pages = paginate(lang, items, page, "ai:mpage", per_page=10)
    text = t(lang, "ai_pick_model", n=len(models), page=page + 1, pages=pages)
    if edit:
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(AISetup.model, F.data.startswith("ai:mpage:"))
async def cb_mpage(cb: CallbackQuery, lang: str):
    await _show_models(cb.message, cb.from_user.id, lang, int(cb.data.split(":")[2]), edit=True)


@router.callback_query(AISetup.model, F.data.startswith("ai:model:"))
async def cb_model(cb: CallbackQuery, state: FSMContext, app: AppContext, lang: str):
    idx = int(cb.data.split(":")[2])
    models = _MODELS.get(cb.from_user.id, [])
    if idx >= len(models):
        return
    await _finish_setup(cb, state, app, lang, models[idx])


@router.message(AISetup.model, F.text)
async def got_model_text(msg: Message, state: FSMContext, app: AppContext, lang: str):
    await _finish_setup(msg, state, app, lang, msg.text.strip())


async def _finish_setup(event, state: FSMContext, app: AppContext, lang: str, model: str):
    data = await state.get_data()
    await state.clear()
    tg_id = event.from_user.id
    if "key" not in data:  # model change only (reconfigure with same credentials)
        cfg = await app.ai_config(tg_id)
        if not cfg:
            await setup_start(event, state, lang)
            return
        data = {"base": cfg["base_url"], "key": cfg["api_key"]}
    await app.save_ai_config(tg_id, data["base"], data["key"], model)
    app.agents.pop(tg_id, None)
    await edit_or_send(event, t(lang, "ai_ready", base=esc(data["base"]), model=esc(model)), ai_home_kb(lang))


# ------------------------------------------------------------------- home
async def _get_agent(app: AppContext, tg_id: int) -> Agent | None:
    cfg = await app.ai_config(tg_id)
    if not cfg:
        return None
    agent = app.agents.get(tg_id)
    if agent and agent.cfg.model == cfg["model"] and agent.cfg.base_url == cfg["base_url"]:
        return agent
    if agent:
        await agent.close()
    u = await app.db.get_user(tg_id)
    gh = await app.gh(tg_id)
    level = LEVELS.get((u["access_level"] if u else "") or "", LEVELS["GHOST"])

    async def events(kind: str, data: dict):
        await _on_event(app, tg_id, kind, data)

    agent = Agent(db=app.db, tg_id=tg_id, cfg=AgentConfig(base_url=cfg["base_url"], api_key=cfg["api_key"], model=cfg["model"],
                                                           max_iterations=app.settings.ai_max_iterations),
                  gh=gh, workspace=app.workspace / str(tg_id), events=events,
                  github_login=(u["gh_login"] if u else "") or "", access_level=level.name)
    app.agents[tg_id] = agent
    return agent


async def show_home(event, app: AppContext, tg_id: int, lang: str):
    agent = await _get_agent(app, tg_id)
    if not agent:
        await edit_or_send(event, t(lang, "ai_not_configured"), rows([ib("⚙️ Setup", "ai:setup")], [ib(t(lang, "btn_menu"), "menu:home")]))
        return
    await agent._ensure()
    row = await app.db.get_session(agent.session_id)
    msgs = await app.db.get_messages(agent.session_id)
    mem = MemoryStore(app.db, tg_id)
    n_mem = len(await mem.entries("memory")) + len(await mem.entries("user"))
    text = t(lang, "ai_home", model=esc(agent.cfg.model), session=agent.session_id, msgs=len(msgs),
             compressions=row["compressions"] if row else 0, mem=n_mem, skills=len(catalog()),
             search="" if app.settings.tavily_key else " (off: no TAVILY key)")
    await edit_or_send(event, text, ai_home_kb(lang))


@entry("ai:home")
async def entry_ai(msg: Message, app: AppContext, lang: str, state: FSMContext):
    await show_home(msg, app, msg.from_user.id, lang)


@router.callback_query(F.data == "ai:home")
async def cb_home(cb: CallbackQuery, app: AppContext, lang: str):
    await show_home(cb, app, cb.from_user.id, lang)


@router.callback_query(F.data == "ai:new")
async def cb_new(cb: CallbackQuery, app: AppContext, lang: str):
    agent = await _get_agent(app, cb.from_user.id)
    if not agent:
        return
    sid = await agent.new_session()
    await app.notifier.send(cb.from_user.id, t(lang, "ai_new_session", id=sid), kind="ai")
    await show_home(cb, app, cb.from_user.id, lang)


@router.message(Command("ai_new"))
async def cmd_new(msg: Message, app: AppContext, lang: str):
    agent = await _get_agent(app, msg.from_user.id)
    if not agent:
        await msg.answer(t(lang, "ai_not_configured"), parse_mode="HTML")
        return
    sid = await agent.new_session()
    await msg.answer(t(lang, "ai_new_session", id=sid), parse_mode="HTML", reply_markup=ai_home_kb(lang))


@router.callback_query(F.data == "ai:sessions")
async def cb_sessions(cb: CallbackQuery, app: AppContext, lang: str):
    agent = await _get_agent(app, cb.from_user.id)
    if not agent:
        return
    await agent._ensure()
    sessions = await app.db.list_sessions(cb.from_user.id, 10)
    body = []
    kb_rows = []
    for s in sessions:
        n = len(await app.db.get_messages(s["id"]))
        active = "▶️" if s["id"] == agent.session_id else "•"
        body.append(t(lang, "ai_session_item", active=active, id=s["id"], title=esc(s["title"] or "—")[:40], msgs=n))
        kb_rows.append([ib(f"{active} {s['id']} {(s['title'] or '')[:25]}", f"ai:switch:{s['id']}")])
    kb_rows.append([ib(t(lang, "btn_back"), "ai:home")])
    await edit_or_send(cb, t(lang, "ai_sessions_title", list="\n".join(body) or "—"), rows(*kb_rows))


@router.callback_query(F.data.startswith("ai:switch:"))
async def cb_switch(cb: CallbackQuery, app: AppContext, lang: str):
    agent = await _get_agent(app, cb.from_user.id)
    if agent and await agent.switch_session(cb.data.split(":")[2]):
        await show_home(cb, app, cb.from_user.id, lang)


@router.callback_query(F.data == "ai:memory")
async def cb_memory(cb: CallbackQuery, app: AppContext, lang: str):
    mem = MemoryStore(app.db, cb.from_user.id)
    m = "\n".join(f"• {esc(e['content'])}" for e in await mem.entries("memory")) or t(lang, "ai_memory_empty")
    u = "\n".join(f"• {esc(e['content'])}" for e in await mem.entries("user")) or t(lang, "ai_memory_empty")
    await edit_or_send(cb, t(lang, "ai_memory_title", memory=m, user=u)[:4000], back_menu(lang, "ai:home"))


@router.callback_query(F.data == "ai:skills")
async def cb_skills(cb: CallbackQuery, lang: str):
    body = "\n".join(t(lang, "ai_skill_item", name=esc(s["name"]), desc=esc(s["description"])[:80]) for s in catalog()) or "—"
    await edit_or_send(cb, t(lang, "ai_skills_title", list=body)[:4000], back_menu(lang, "ai:home"))


@router.callback_query(F.data == "ai:stop")
async def cb_stop(cb: CallbackQuery, app: AppContext, lang: str):
    await _stop(app, cb.from_user.id, lang)


@router.message(Command("ai_stop", "stop"))
async def cmd_stop(msg: Message, app: AppContext, lang: str):
    await _stop(app, msg.from_user.id, lang)


async def _stop(app: AppContext, tg_id: int, lang: str):
    agent = app.agents.get(tg_id)
    task = app.ai_tasks.get(tg_id)
    if agent:
        agent.cancel.set()
    if task and not task.done():
        task.cancel()
    await app.db.clear_pending(tg_id)
    await app.notifier.send(tg_id, t(lang, "ai_stopped"), kind="ai")


@router.callback_query(F.data.startswith("ai:repo:"))
async def cb_ai_repo(cb: CallbackQuery, app: AppContext, lang: str):
    full = repo_from_id(cb.data.split(":")[2])
    if full:
        await ask(app, cb.from_user.id, cb.message.chat.id, lang,
                  f"Give me a concise overview of the repository {full}: purpose, structure, workflows, referenced secrets, "
                  f"open issues/PRs, and anything that looks wrong. Use github_api.")


# ------------------------------------------------------------------- chat
@router.message(Command("ai"))
async def cmd_ai(msg: Message, app: AppContext, lang: str):
    parts = (msg.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await show_home(msg, app, msg.from_user.id, lang)
        return
    await ask(app, msg.from_user.id, msg.chat.id, lang, parts[1])


@router.message(F.document | F.photo)
async def got_file(msg: Message, state: FSMContext, app: AppContext, lang: str):
    """Record the latest incoming file so telegram_download_file can fetch it."""
    if await state.get_state():
        return  # another flow owns this message (e.g. upload wizard)
    file_id = None
    fname = None
    if msg.document:
        file_id = msg.document.file_id
        fname = msg.document.file_name
    elif msg.photo:
        file_id = msg.photo[-1].file_id
        fname = f"photo_{msg.photo[-1].width}x{msg.photo[-1].height}.jpg"
    if not file_id:
        return
    await app.db.kv_set(f"incoming:{msg.from_user.id}", {"file_id": file_id, "name": fname, "ts": __import__("time").time()})
    await app.notifier.send(msg.chat.id, t(lang, "ai_file_received", name=esc(fname or "file")), kind="ai", store=False)


@router.message(F.text & ~F.text.startswith("/") & ~F.text.in_(set(BUTTONS)))
async def free_text(msg: Message, state: FSMContext, app: AppContext, lang: str):
    if await state.get_state():
        return  # another flow owns this text
    cfg = await app.ai_config(msg.from_user.id)
    if not cfg:
        await msg.answer(t(lang, "unknown"), parse_mode="HTML")
        return
    await ask(app, msg.from_user.id, msg.chat.id, lang, msg.text)


async def ask(app: AppContext, tg_id: int, chat_id: int, lang: str, text: str, *, resume: bool = False):
    task = app.ai_tasks.get(tg_id)
    if task and not task.done():
        await app.notifier.send(chat_id, t(lang, "ai_busy"), kind="ai", markup=ai_stop_kb(lang), store=False)
        return
    agent = await _get_agent(app, tg_id)
    if not agent:
        await app.notifier.send(chat_id, t(lang, "ai_not_configured"), kind="ai")
        return
    app.ai_tasks[tg_id] = asyncio.create_task(_run(app, agent, tg_id, chat_id, lang, text, resume))


async def _run(app: AppContext, agent: Agent, tg_id: int, chat_id: int, lang: str, text: str | None, resume: bool):
    status = await app.notifier.send(chat_id, t(lang, "ai_thinking"), kind="ai", markup=ai_stop_kb(lang), store=False)
    app.agents[tg_id].extra_status = (chat_id, status.message_id if status else None)  # type: ignore[attr-defined]
    try:
        result: RunResult = await agent.run(text, resume=resume)
    except asyncio.CancelledError:
        return
    except Exception as e:
        log.exception("agent crashed")
        await app.notifier.send(chat_id, t(lang, "error_generic", error=esc(str(e)[:300])), kind="error")
        return
    if result.stopped:
        return
    if result.error:
        await app.notifier.send(chat_id, t(lang, "error_generic", error=esc(result.error[:400])), kind="error", markup=ai_home_kb(lang))
        return
    if result.text:
        await app.notifier.send(chat_id, _md_to_html(result.text), kind="ai")
    if result.hit_max:
        await app.notifier.send(chat_id, t(lang, "ai_max_iter", n=agent.cfg.max_iterations), kind="ai")
    await app.notifier.send(chat_id, t(lang, "ai_done", iters=result.iterations, tools=result.tool_calls), kind="ai",
                            markup=ai_home_kb(lang), store=False)


async def _on_event(app: AppContext, tg_id: int, kind: str, data: dict):
    lang = await app.lang(tg_id)
    chat_id = tg_id
    agent = app.agents.get(tg_id)
    st = getattr(agent, "extra_status", (chat_id, None))
    if kind == "thinking":
        if st[1]:
            await app.notifier.edit(st[0], st[1], t(lang, "ai_thinking") + f" (step {data.get('iteration')})", ai_stop_kb(lang))
    elif kind == "tool_call":
        args = data.get("args", "")
        try:
            a = json.loads(args)
            short = ", ".join(f"{k}={str(v)[:60]}" for k, v in list(a.items())[:4])
        except Exception:
            short = args[:120]
        await app.notifier.send(chat_id, t(lang, "ai_tool_call", tool=esc(data["name"]), args=esc(short)), kind="ai_step", store=False)
    elif kind == "tool_result":
        res = data.get("result", "")
        try:
            r = json.loads(res)
            if isinstance(r, dict) and r.get("error"):
                summary = "❌ " + str(r["error"])[:200]
            elif isinstance(r, dict) and "exit_code" in r:
                summary = f"exit {r['exit_code']} · {len(r.get('output', ''))} chars"
            else:
                summary = (json.dumps(r, ensure_ascii=False)[:160]) if not isinstance(r, str) else r[:160]
        except Exception:
            summary = res[:160]
        if data["name"] not in ("todo_list",):
            await app.notifier.send(chat_id, t(lang, "ai_tool_result", tool=esc(data["name"]), summary=esc(summary)), kind="ai_step", store=False)
    elif kind == "tool_notify":
        await app.notifier.send(chat_id, data.get("text", ""), kind="ai_step", store=False)
    elif kind == "assistant_text":
        await app.notifier.send(chat_id, _md_to_html(data.get("text", "")), kind="ai", store=False)
    elif kind == "rate_limited":
        await app.notifier.send(chat_id, t(lang, "ai_rate_limited", secs=data.get("secs"), n=data.get("attempt")), kind="ai", store=False)
    elif kind == "api_retry":
        await app.notifier.send(chat_id, t(lang, "ai_api_error", error=esc(data.get("kind", "")), secs=data.get("secs")), kind="ai", store=False)
    elif kind == "compressing":
        await app.notifier.send(chat_id, t(lang, "ai_compressing"), kind="ai", store=False)
    elif kind == "error":
        pass  # surfaced by _run


def _md_to_html(text: str) -> str:
    """Minimal markdown → Telegram HTML (bold, code, code blocks, links); everything else escaped."""
    blocks = re.split(r"```(?:\w+)?\n?(.*?)```", text, flags=re.S)
    out = []
    for i, part in enumerate(blocks):
        if i % 2 == 1:
            out.append(f"<pre>{esc(part.rstrip())}</pre>")
            continue
        p = esc(part)
        p = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", p)
        p = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", p)
        p = re.sub(r"(?m)^#{1,6}\s+(.+)$", r"<b>\1</b>", p)
        p = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', p)
        out.append(p)
    return "".join(out)


async def resume_pending(app: AppContext):
    """Called at startup: continue any GITHUB_AI task interrupted by a restart."""
    for p in await app.db.all_pending():
        tg_id = p["tg_id"]
        lang = await app.lang(tg_id)
        await app.notifier.send(tg_id, t(lang, "lifecycle_resume_ai"), kind="ai")
        agent = await _get_agent(app, tg_id)
        if not agent:
            await app.db.clear_pending(tg_id)
            continue
        await agent.switch_session(p["session_id"])
        msgs = await app.db.get_messages(p["session_id"])
        # Repair the tail so tool calls and tool results stay paired. If the run was interrupted while tools were
        # executing, the last assistant turn may have 0..n-1 of its n results persisted → the provider would
        # reject the request. Drop that assistant turn (and its partial results) so the model re-issues the calls.
        last_call = next((i for i in range(len(msgs) - 1, -1, -1)
                          if msgs[i]["role"] == "assistant" and msgs[i].get("tool_calls")), None)
        if last_call is not None:
            expected = {tc["id"] for tc in msgs[last_call]["tool_calls"]}
            got = {m.get("tool_call_id") for m in msgs[last_call + 1:] if m["role"] == "tool"}
            if not expected.issubset(got) and all(m["role"] == "tool" for m in msgs[last_call + 1:]):
                msgs = msgs[:last_call]
                await app.db.replace_messages(p["session_id"], msgs)
        if msgs and msgs[-1]["role"] in ("user", "tool"):
            await ask(app, tg_id, tg_id, lang, None, resume=True)
        else:
            await app.db.clear_pending(tg_id)
