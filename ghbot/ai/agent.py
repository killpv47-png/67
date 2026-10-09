"""GITHUB_AI conversation loop (adapted from Hermes ``run_agent.py`` / ``agent/conversation_loop.py``).

Invariants kept from Hermes:
  * system prompt is built once per session and frozen (rebuilt only after compression)
  * strict role alternation; tool calls and tool results stay paired
  * independent tool calls in one assistant turn run concurrently
  * context compression is the ONLY thing that mutates past history

Additions for this project:
  * every iteration persists a ``pending`` record so an interrupted run (rate
    limit beyond budget, workflow restart) resumes from the same point
  * each step emits a Telegram notification through ``events``
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from ..core.config import settings
from ..core.crypto import new_session_id
from ..core.db import Database
from ..github.client import GitHubClient
from . import prompt_builder, skills
from .compressor import ContextCompressor
from .llm import LLMClient, LLMError
from .memory import MemoryStore
from .tools import ToolContext, dispatch, tool_schemas

log = logging.getLogger(__name__)

EventCB = Callable[[str, dict], Awaitable[None]]


@dataclass
class AgentConfig:
    base_url: str
    api_key: str
    model: str
    context_length: int = 128_000
    max_iterations: int = 60
    temperature: float = 0.2


@dataclass
class RunResult:
    text: str
    iterations: int
    tool_calls: int
    stopped: bool = False
    error: str | None = None
    hit_max: bool = False


@dataclass
class Agent:
    db: Database
    tg_id: int
    cfg: AgentConfig
    gh: Optional[GitHubClient]
    workspace: Path
    events: EventCB
    github_login: str = ""
    access_level: str = ""
    session_id: str = ""
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    _llm: LLMClient | None = None
    _ctx: ToolContext | None = None
    _system_prompt: str = ""

    # ----------------------------------------------------------- lifecycle
    async def _emit(self, event_kind: str, **data):
        try:
            await self.events(event_kind, data)
        except Exception:  # UI must never break the loop
            log.exception("event handler failed")

    async def _on_wait(self, secs: float, kind: str, attempt: int):
        await self._emit("rate_limited" if kind == "rate_limit" else "api_retry", secs=int(secs), attempt=attempt, kind=kind)

    async def _ensure(self):
        if self._llm is None:
            self._llm = LLMClient(self.cfg.base_url, self.cfg.api_key, on_wait=self._on_wait)
        self.workspace.mkdir(parents=True, exist_ok=True)
        if not self.session_id:
            sessions = await self.db.list_sessions(self.tg_id, limit=1)
            active = await self.db.kv_get(f"active_session:{self.tg_id}")
            self.session_id = active or (sessions[0]["id"] if sessions else "")
        if not self.session_id or not await self.db.get_session(self.session_id):
            await self.new_session()
        if self._ctx is None:
            self._ctx = ToolContext(
                db=self.db, tg_id=self.tg_id, session_id=self.session_id, workspace=self.workspace,
                memory=MemoryStore(self.db, self.tg_id), gh=self.gh, tavily_key=settings.tavily_key,
                host_repo=settings.host_repo, bot_token=settings.bot_token,
                incoming_file=await self.db.kv_get(f"incoming:{self.tg_id}"),
                notify=lambda text: self._emit("tool_notify", text=text),
            )
            self._ctx.todos = await self.db.kv_get(f"todo:{self.session_id}", [])
        row = await self.db.get_session(self.session_id)
        self._system_prompt = row["system_prompt"] or await self._build_prompt()
        if not row["system_prompt"]:
            await self.db.update_session(self.session_id, system_prompt=self._system_prompt, model=self.cfg.model)

    async def _build_prompt(self) -> str:
        mem = MemoryStore(self.db, self.tg_id)
        return prompt_builder.build_system_prompt(
            model=self.cfg.model, session_id=self.session_id, skills_index=skills.skills_index_block(),
            memory_block=await mem.render("memory"), user_block=await mem.render("user"), workspace=self.workspace,
            in_actions=settings.in_actions, host_repo=settings.host_repo, run_id=settings.run_id,
            has_web_search=bool(settings.tavily_key), github_login=self.github_login, access_level=self.access_level,
        )

    async def new_session(self) -> str:
        self.session_id = new_session_id()
        await self.db.create_session(self.session_id, self.tg_id, self.cfg.model, None)
        await self.db.kv_set(f"active_session:{self.tg_id}", self.session_id)
        if self._ctx:
            self._ctx.session_id = self.session_id
            self._ctx.todos = []
        self._system_prompt = ""
        return self.session_id

    async def switch_session(self, session_id: str) -> bool:
        if not await self.db.get_session(session_id):
            return False
        self.session_id = session_id
        await self.db.kv_set(f"active_session:{self.tg_id}", session_id)
        if self._ctx:
            self._ctx.session_id = session_id
        self._system_prompt = ""
        return True

    async def close(self):
        if self._llm:
            await self._llm.aclose()

    # ----------------------------------------------------------------- run
    async def run(self, user_text: str | None, *, resume: bool = False) -> RunResult:
        """Process one user turn.  ``resume=True`` continues an interrupted turn
        (no new user message is appended)."""
        await self._ensure()
        assert self._llm and self._ctx
        self.cancel.clear()
        messages = await self.db.get_messages(self.session_id)
        if user_text is not None and not resume:
            if messages and messages[-1]["role"] == "user":
                # alternation guard: merge consecutive user messages
                messages[-1]["content"] = f"{messages[-1]['content']}\n\n{user_text}"
                await self.db.replace_messages(self.session_id, messages)
            else:
                await self.db.add_message(self.session_id, {"role": "user", "content": user_text})
                messages.append({"role": "user", "content": user_text})
            row = await self.db.get_session(self.session_id)
            if not row["title"]:
                await self.db.update_session(self.session_id, title=user_text.strip().split("\n")[0][:60])

        compressor = ContextCompressor(self._llm, self.cfg.model, context_length=self.cfg.context_length)
        tools = tool_schemas(self._ctx)
        iterations = 0
        tool_calls_total = 0
        final_text = ""
        max_iter = self.cfg.max_iterations

        while iterations < max_iter:
            if self.cancel.is_set():
                await self.db.clear_pending(self.tg_id)
                return RunResult(final_text, iterations, tool_calls_total, stopped=True)
            iterations += 1
            await self.db.set_pending(self.tg_id, self.session_id, {"phase": "llm", "iteration": iterations, "ts": time.time()})

            # proactive compression
            if compressor.needs_compression(self._system_prompt, messages):
                await self._emit("compressing")
                messages, changed = await compressor.compress(self._system_prompt, messages)
                if changed:
                    await self.db.replace_messages(self.session_id, messages)
                    self._system_prompt = await self._build_prompt()
                    await self.db.update_session(self.session_id, system_prompt=self._system_prompt)

            await self._emit("thinking", iteration=iterations)
            try:
                resp = await self._llm.chat(
                    model=self.cfg.model, messages=[{"role": "system", "content": self._system_prompt}, *messages],
                    tools=tools, temperature=self.cfg.temperature, cancel=self.cancel,
                )
            except asyncio.CancelledError:
                await self.db.clear_pending(self.tg_id)
                return RunResult(final_text, iterations, tool_calls_total, stopped=True)
            except LLMError as e:
                if e.kind == "context_length":
                    await self._emit("compressing", forced=True)
                    messages, changed = await compressor.compress(self._system_prompt, messages, force=True)
                    if changed:
                        await self.db.replace_messages(self.session_id, messages)
                        continue
                    # last resort: drop oldest non-head turns
                    if len(messages) > 3:
                        messages = [messages[0]] + messages[-2:]
                        await self.db.replace_messages(self.session_id, messages)
                        continue
                if e.kind == "exhausted":
                    # keep pending so a later run/resume can continue exactly here
                    await self._emit("error", error=str(e), resumable=True)
                    return RunResult(final_text, iterations, tool_calls_total, error=f"[{e.kind}] {e}")
                await self.db.clear_pending(self.tg_id)
                await self._emit("error", error=str(e), kind=e.kind)
                return RunResult(final_text, iterations, tool_calls_total, error=f"[{e.kind}] {e}")

            assistant_msg = resp.as_message()
            if not resp.tool_calls and not (resp.content or "").strip():
                # empty response guard (Hermes empty_response_guard): nudge once
                if iterations < max_iter:
                    messages.append({"role": "assistant", "content": "(empty)"})
                    messages.append({"role": "user", "content": "Your last response was empty. Continue the task or give your final answer."})
                    await self.db.add_message(self.session_id, messages[-2])
                    await self.db.add_message(self.session_id, messages[-1])
                    continue
            messages.append(assistant_msg)
            await self.db.add_message(self.session_id, assistant_msg)

            if not resp.tool_calls:
                final_text = resp.content or ""
                break

            # ---- execute tool calls (concurrently, like Hermes)
            if resp.content and resp.content.strip():
                await self._emit("assistant_text", text=resp.content)
            await self.db.set_pending(self.tg_id, self.session_id, {"phase": "tools", "iteration": iterations, "ts": time.time()})
            calls = self._dedupe(resp.tool_calls)
            tool_calls_total += len(calls)
            for tc in calls:
                await self._emit("tool_call", name=tc["function"]["name"], args=tc["function"]["arguments"])

            async def run_one(tc):
                return tc, await dispatch(self._ctx, tc["function"]["name"], tc["function"]["arguments"])

            results = await asyncio.gather(*(run_one(tc) for tc in calls))
            for tc, result in results:
                tool_msg = {"role": "tool", "tool_call_id": tc["id"], "name": tc["function"]["name"], "content": result}
                messages.append(tool_msg)
                await self.db.add_message(self.session_id, tool_msg)
                await self._emit("tool_result", name=tc["function"]["name"], result=result)
            # tool_calls the model listed but we deduped still need a result for alternation safety
            seen = {tc["id"] for tc in calls}
            for tc in resp.tool_calls:
                if tc["id"] not in seen:
                    tool_msg = {"role": "tool", "tool_call_id": tc["id"], "name": tc["function"]["name"],
                                "content": json.dumps({"skipped": "duplicate call in the same turn"})}
                    messages.append(tool_msg)
                    await self.db.add_message(self.session_id, tool_msg)

        await self.db.clear_pending(self.tg_id)
        hit_max = iterations >= max_iter and not final_text
        return RunResult(final_text, iterations, tool_calls_total, hit_max=hit_max)

    @staticmethod
    def _dedupe(tool_calls: list[dict]) -> list[dict]:
        seen: set[tuple[str, str]] = set()
        out = []
        for tc in tool_calls:
            key = (tc["function"]["name"], tc["function"]["arguments"])
            if key in seen:
                continue
            seen.add(key)
            out.append(tc)
        return out
