"""Tool registry for GITHUB_AI.

Each tool = OpenAI function schema + async handler ``(ctx, args) -> str``.
``ctx`` is ``ToolContext`` (see ``context.py``) carrying the user's DB handle,
GitHub client, workspace path, memory store and notifier.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from .context import ToolContext
from . import terminal_tool, file_tools, web_tools, github_tool, todo_tool, session_tool, telegram_file_tool, telegram_download_tool
from .. import memory as memory_mod
from .. import skills as skills_mod

log = logging.getLogger(__name__)

Handler = Callable[[ToolContext, dict], Awaitable[str]]


async def _memory(ctx: ToolContext, args: dict) -> str:
    return await memory_mod.memory_tool(ctx.memory, args)


async def _skills_list(ctx: ToolContext, args: dict) -> str:
    return skills_mod.skills_list(args.get("category"))


async def _skill_view(ctx: ToolContext, args: dict) -> str:
    return skills_mod.skill_view(args.get("name", ""), args.get("file_path"))


async def _skill_manage(ctx: ToolContext, args: dict) -> str:
    return skills_mod.skill_manage(args.get("operations") or [])


TOOLS: dict[str, tuple[dict, Handler]] = {
    "terminal": (terminal_tool.SCHEMA, terminal_tool.handle),
    "read_file": (file_tools.READ_SCHEMA, file_tools.read_file),
    "write_file": (file_tools.WRITE_SCHEMA, file_tools.write_file),
    "patch": (file_tools.PATCH_SCHEMA, file_tools.patch),
    "search_files": (file_tools.SEARCH_SCHEMA, file_tools.search_files),
    "github_api": (github_tool.SCHEMA, github_tool.handle),
    "web_search": (web_tools.SEARCH_SCHEMA, web_tools.web_search),
    "web_extract": (web_tools.EXTRACT_SCHEMA, web_tools.web_extract),
    "memory": (memory_mod.MEMORY_SCHEMA, _memory),
    "skills_list": (skills_mod.SKILLS_LIST_SCHEMA, _skills_list),
    "skill_view": (skills_mod.SKILL_VIEW_SCHEMA, _skill_view),
    "skill_manage": (skills_mod.SKILL_MANAGE_SCHEMA, _skill_manage),
    "todo_list": (todo_tool.SCHEMA, todo_tool.handle),
    "session_search": (session_tool.SCHEMA, session_tool.handle),
    "telegram_send_file": (telegram_file_tool.SCHEMA, telegram_file_tool.handle),
    "telegram_download_file": (telegram_download_tool.SCHEMA, telegram_download_tool.handle),
}

MAX_RESULT_CHARS = {"terminal": 30_000, "read_file": 40_000, "job_log": 12_000}
DEFAULT_MAX_RESULT = 20_000


def tool_schemas(ctx: ToolContext) -> list[dict]:
    out = []
    for name, (schema, _) in TOOLS.items():
        if name in ("web_search", "web_extract") and not ctx.tavily_key:
            continue
        out.append({"type": "function", "function": schema})
    return out


def truncate_result(name: str, text: str) -> str:
    limit = MAX_RESULT_CHARS.get(name, DEFAULT_MAX_RESULT)
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    tail = int(limit * 0.25)
    return text[:head] + f"\n\n[... output truncated: {len(text) - head - tail} chars omitted ...]\n\n" + text[-tail:]


async def dispatch(ctx: ToolContext, name: str, arguments: str) -> str:
    entry = TOOLS.get(name)
    if not entry:
        return json.dumps({"error": f"unknown tool '{name}'", "available": list(TOOLS)})
    try:
        args = json.loads(arguments) if arguments else {}
        if not isinstance(args, dict):
            args = {}
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"invalid JSON arguments: {e}"})
    try:
        result = await entry[1](ctx, args)
    except Exception as e:  # tools must never crash the loop
        log.exception("tool %s failed", name)
        result = json.dumps({"error": f"{type(e).__name__}: {e}"})
    return truncate_result(name, ctx.redact(result))
