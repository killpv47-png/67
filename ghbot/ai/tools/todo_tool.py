"""todo_list — Hermes todo tool. The list is per session and stored in the DB kv so it survives restarts."""

from __future__ import annotations

import json

from .context import ToolContext

SCHEMA = {
    "name": "todo_list",
    "description": (
        "Track a task list for multi-step work (3+ steps). Call with no parameters to read the current list. "
        "List order is priority. Only ONE item in_progress at a time. Mark an item completed only after the work is "
        "verified done, never based on intent. If something fails, cancel it and add a revised item. Always returns "
        "the full current list. The user sees this list as live progress in Telegram."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "description": "Full replacement list.",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "content": {"type": "string"},
                        "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]},
                    },
                    "required": ["id", "content", "status"],
                },
            }
        },
    },
}

ICON = {"pending": "⬜", "in_progress": "🔄", "completed": "✅", "cancelled": "🚫"}


def render(todos: list[dict]) -> str:
    if not todos:
        return ""
    return "\n".join(f"{ICON.get(t.get('status'), '•')} {t.get('content', '')}" for t in todos)


async def handle(ctx: ToolContext, args: dict) -> str:
    key = f"todo:{ctx.session_id}"
    if args.get("todos") is not None:
        todos = [t for t in args["todos"] if isinstance(t, dict) and t.get("content")]
        in_prog = [t for t in todos if t.get("status") == "in_progress"]
        warn = None
        if len(in_prog) > 1:
            warn = "more than one in_progress item; keep exactly one"
        ctx.todos = todos
        await ctx.db.kv_set(key, todos)
        if ctx.notify:
            await ctx.notify("📋 <b>Plan</b>\n" + render(todos))
        return json.dumps({"todos": todos, "warning": warn}, ensure_ascii=False)
    todos = await ctx.db.kv_get(key, [])
    ctx.todos = todos
    return json.dumps({"todos": todos}, ensure_ascii=False)
