"""session_search — FTS5 search over this user's past AI conversations."""

from __future__ import annotations

import json
import time

from .context import ToolContext

SCHEMA = {
    "name": "session_search",
    "description": (
        "Search your past conversations with this user (full-text). Use when the user references earlier work "
        "('like last time', 'the repo we set up') before asking them to repeat it."
    ),
    "parameters": {
        "type": "object",
        "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 8}},
        "required": ["query"],
    },
}


async def handle(ctx: ToolContext, args: dict) -> str:
    rows = await ctx.db.search_messages(ctx.tg_id, args.get("query", ""), int(args.get("limit") or 8))
    out = []
    for r in rows:
        if r["session_id"] == ctx.session_id:
            continue
        age_h = int((time.time() - (r.get("updated_at") or time.time())) / 3600)
        out.append({"session": r["session_id"], "title": r.get("title"), "age_hours": age_h, "snippet": (r["content"] or "")[:400]})
    return json.dumps({"results": out}, ensure_ascii=False)
