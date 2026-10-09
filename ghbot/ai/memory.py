"""Hermes-style memory: MEMORY (agent notes) + USER (profile).

Both are rendered into the system prompt as a FROZEN snapshot at session start;
mid-session writes hit the DB but do not mutate the cached prompt (prefix cache
stays intact) — exactly like Hermes ``tools/memory_tool.py``.
"""

from __future__ import annotations

import json

from ..core.db import Database
from ..core.redact import redact

MEMORY_CHAR_LIMIT = 2200
USER_CHAR_LIMIT = 1375
LIMITS = {"memory": MEMORY_CHAR_LIMIT, "user": USER_CHAR_LIMIT}


class MemoryStore:
    def __init__(self, db: Database, tg_id: int):
        self.db = db
        self.tg_id = tg_id

    async def entries(self, target: str) -> list[dict]:
        return [{"id": r["id"], "content": r["content"]} for r in await self.db.memory_list(self.tg_id, target)]

    async def used(self, target: str) -> int:
        return sum(len(e["content"]) + 1 for e in await self.entries(target))

    async def render(self, target: str) -> str:
        entries = await self.entries(target)
        if not entries:
            return ""
        title = "## Persistent Memory" if target == "memory" else "## User Profile"
        return title + "\n" + "\n".join(f"- {e['content']}" for e in entries)

    async def add(self, target: str, content: str) -> dict:
        content = redact(content.strip())
        if not content:
            return {"success": False, "error": "empty content"}
        used = await self.used(target)
        limit = LIMITS[target]
        if used + len(content) + 1 > limit:
            return {"success": False, "error": f"{target} budget exceeded ({used}/{limit} chars). Replace or remove stale entries first.",
                    "entries": await self.entries(target)}
        await self.db.memory_add(self.tg_id, target, content)
        return {"success": True, "used": used + len(content) + 1, "limit": limit}

    async def _find(self, target: str, old_text: str) -> dict | None:
        matches = [e for e in await self.entries(target) if old_text in e["content"]]
        if len(matches) == 1:
            return matches[0]
        return None

    async def replace(self, target: str, old_text: str, content: str) -> dict:
        e = await self._find(target, old_text)
        if not e:
            return {"success": False, "error": "old_text must match exactly one entry", "entries": await self.entries(target)}
        await self.db.memory_update(e["id"], redact(content.strip()))
        return {"success": True}

    async def remove(self, target: str, old_text: str) -> dict:
        e = await self._find(target, old_text)
        if not e:
            return {"success": False, "error": "old_text must match exactly one entry", "entries": await self.entries(target)}
        await self.db.memory_delete(e["id"])
        return {"success": True}


MEMORY_SCHEMA = {
    "name": "memory",
    "description": (
        "Persistent memory across sessions. target='memory' = facts about the environment/conventions that apply to "
        "every session; target='user' = durable facts about the user (name, preferences, GitHub habits). Entries are "
        "declarative facts, char-budgeted (memory 2200, user 1375). Actions: add(content), replace(old_text, content), "
        "remove(old_text). Never store secrets."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "replace", "remove"]},
            "target": {"type": "string", "enum": ["memory", "user"], "default": "memory"},
            "content": {"type": "string", "description": "Entry text (add/replace)."},
            "old_text": {"type": "string", "description": "Substring uniquely identifying the entry (replace/remove)."},
        },
        "required": ["action"],
    },
}


async def memory_tool(store: MemoryStore, args: dict) -> str:
    action = args.get("action")
    target = args.get("target", "memory")
    if target not in LIMITS:
        return json.dumps({"success": False, "error": "target must be memory|user"})
    if action == "add":
        res = await store.add(target, args.get("content", ""))
    elif action == "replace":
        res = await store.replace(target, args.get("old_text", ""), args.get("content", ""))
    elif action == "remove":
        res = await store.remove(target, args.get("old_text", ""))
    else:
        res = {"success": False, "error": "unknown action"}
    return json.dumps(res, ensure_ascii=False)
