"""Local database (SQLite, WAL mode, FTS5).

Why SQLite: it lives inside the runner, survives the run as an encrypted checkpoint
pushed to the host repo (see lifecycle/), needs zero network, and gives us FTS5 for
Hermes-style ``session_search`` for free.

Tables
  users            telegram user -> language, role, encrypted GitHub PAT, access level
  kv               generic key/value (ai config per user, flags, last_run, ...)
  notifications    every notification the bot sent (audit + "re-send" button)
  jobs             long-running tasks (uploads, AI runs) with step-by-step progress
  watches          repos/workflows the user wants run-status notifications for
  ai_sessions      one row per AI conversation (system prompt frozen per session)
  ai_messages      chat history (role/content/tool_calls JSON) + FTS5 mirror
  ai_memory        MEMORY.md / USER.md entries (Hermes memory tool, char-budgeted)
  ai_pending       the in-flight AI request that must be resumed after a rate-limit or restart
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable, Optional

import aiosqlite

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
  tg_id         INTEGER PRIMARY KEY,
  username      TEXT,
  lang          TEXT NOT NULL DEFAULT 'en',
  role          TEXT NOT NULL DEFAULT 'user',
  gh_token_enc  BLOB,
  gh_login      TEXT,
  gh_scopes     TEXT,
  access_level  TEXT,
  created_at    REAL NOT NULL,
  updated_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_id     INTEGER NOT NULL,
  kind      TEXT NOT NULL,
  text      TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(tg_id, created_at DESC);

CREATE TABLE IF NOT EXISTS jobs (
  id         TEXT PRIMARY KEY,
  tg_id      INTEGER NOT NULL,
  kind       TEXT NOT NULL,
  status     TEXT NOT NULL,
  title      TEXT NOT NULL,
  payload    TEXT NOT NULL DEFAULT '{}',
  steps      TEXT NOT NULL DEFAULT '[]',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(tg_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS watches (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_id      INTEGER NOT NULL,
  repo       TEXT NOT NULL,
  last_run_id INTEGER,
  last_status TEXT,
  created_at REAL NOT NULL,
  UNIQUE(tg_id, repo)
);

CREATE TABLE IF NOT EXISTS ai_sessions (
  id            TEXT PRIMARY KEY,
  tg_id         INTEGER NOT NULL,
  title         TEXT,
  model         TEXT,
  system_prompt TEXT,
  compressions  INTEGER NOT NULL DEFAULT 0,
  created_at    REAL NOT NULL,
  updated_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sess_user ON ai_sessions(tg_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS ai_messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id  TEXT NOT NULL REFERENCES ai_sessions(id) ON DELETE CASCADE,
  role        TEXT NOT NULL,
  content     TEXT,
  tool_calls  TEXT,
  tool_call_id TEXT,
  name        TEXT,
  created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_sess ON ai_messages(session_id, id);

CREATE VIRTUAL TABLE IF NOT EXISTS ai_messages_fts USING fts5(
  content, session_id UNINDEXED, msg_id UNINDEXED, tokenize='unicode61'
);

CREATE TABLE IF NOT EXISTS ai_memory (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_id      INTEGER NOT NULL,
  target     TEXT NOT NULL,          -- 'memory' | 'user'
  content    TEXT NOT NULL,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mem_user ON ai_memory(tg_id, target);

CREATE TABLE IF NOT EXISTS ai_pending (
  tg_id       INTEGER PRIMARY KEY,
  session_id  TEXT NOT NULL,
  state       TEXT NOT NULL,         -- JSON: {phase, retry_count, resume_after, chat_id, status_msg_id}
  updated_at  REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._conn: Optional[aiosqlite.Connection] = None

    async def open(self) -> "Database":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path, isolation_level=None)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        return self

    async def close(self) -> None:
        if self._conn:
            await self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database not opened"
        return self._conn

    async def checkpoint(self) -> None:
        """Flush WAL into the main file so the .db file alone is a complete snapshot."""
        await self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    # ------------------------------------------------------------------ users
    async def upsert_user(self, tg_id: int, username: str | None = None) -> aiosqlite.Row:
        now = time.time()
        await self.conn.execute(
            """INSERT INTO users(tg_id, username, created_at, updated_at) VALUES(?,?,?,?)
               ON CONFLICT(tg_id) DO UPDATE SET username=COALESCE(excluded.username, users.username), updated_at=excluded.updated_at""",
            (tg_id, username, now, now),
        )
        return await self.get_user(tg_id)

    async def get_user(self, tg_id: int) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,))
        return await cur.fetchone()

    async def count_users(self) -> int:
        cur = await self.conn.execute("SELECT COUNT(*) FROM users")
        return (await cur.fetchone())[0]

    async def set_user_fields(self, tg_id: int, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k}=?" for k in fields)
        await self.conn.execute(f"UPDATE users SET {cols} WHERE tg_id=?", (*fields.values(), tg_id))

    async def all_users(self) -> list[aiosqlite.Row]:
        cur = await self.conn.execute("SELECT * FROM users")
        return list(await cur.fetchall())

    # --------------------------------------------------------------------- kv
    async def kv_get(self, key: str, default: Any = None) -> Any:
        cur = await self.conn.execute("SELECT v FROM kv WHERE k=?", (key,))
        row = await cur.fetchone()
        return json.loads(row[0]) if row else default

    async def kv_set(self, key: str, value: Any) -> None:
        await self.conn.execute(
            "INSERT INTO kv(k,v,updated_at) VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated_at=excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), time.time()),
        )

    async def kv_delete(self, key: str) -> None:
        await self.conn.execute("DELETE FROM kv WHERE k=?", (key,))

    # ------------------------------------------------------------ notifications
    async def add_notification(self, tg_id: int, kind: str, text: str) -> int:
        cur = await self.conn.execute(
            "INSERT INTO notifications(tg_id, kind, text, created_at) VALUES(?,?,?,?)",
            (tg_id, kind, text, time.time()),
        )
        await self.conn.execute(
            "DELETE FROM notifications WHERE tg_id=? AND id NOT IN (SELECT id FROM notifications WHERE tg_id=? ORDER BY id DESC LIMIT 500)",
            (tg_id, tg_id),
        )
        return cur.lastrowid or 0

    async def recent_notifications(self, tg_id: int, limit: int = 20) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM notifications WHERE tg_id=? ORDER BY id DESC LIMIT ?", (tg_id, limit)
        )
        return list(await cur.fetchall())

    # ------------------------------------------------------------------- jobs
    async def create_job(self, job_id: str, tg_id: int, kind: str, title: str, payload: dict | None = None) -> None:
        now = time.time()
        await self.conn.execute(
            "INSERT INTO jobs(id,tg_id,kind,status,title,payload,steps,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (job_id, tg_id, kind, "running", title, json.dumps(payload or {}, ensure_ascii=False), "[]", now, now),
        )

    async def job_step(self, job_id: str, text: str, ok: bool = True) -> None:
        cur = await self.conn.execute("SELECT steps FROM jobs WHERE id=?", (job_id,))
        row = await cur.fetchone()
        if not row:
            return
        steps = json.loads(row[0])
        steps.append({"t": time.time(), "text": text, "ok": ok})
        await self.conn.execute(
            "UPDATE jobs SET steps=?, updated_at=? WHERE id=?", (json.dumps(steps, ensure_ascii=False), time.time(), job_id)
        )

    async def finish_job(self, job_id: str, status: str = "done") -> None:
        await self.conn.execute("UPDATE jobs SET status=?, updated_at=? WHERE id=?", (status, time.time(), job_id))

    async def get_job(self, job_id: str) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,))
        return await cur.fetchone()

    async def recent_jobs(self, tg_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        cur = await self.conn.execute("SELECT * FROM jobs WHERE tg_id=? ORDER BY updated_at DESC LIMIT ?", (tg_id, limit))
        return list(await cur.fetchall())

    # ---------------------------------------------------------------- watches
    async def add_watch(self, tg_id: int, repo: str) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO watches(tg_id, repo, created_at) VALUES(?,?,?)", (tg_id, repo, time.time())
        )

    async def remove_watch(self, tg_id: int, repo: str) -> None:
        await self.conn.execute("DELETE FROM watches WHERE tg_id=? AND repo=?", (tg_id, repo))

    async def list_watches(self, tg_id: int | None = None) -> list[aiosqlite.Row]:
        if tg_id is None:
            cur = await self.conn.execute("SELECT * FROM watches")
        else:
            cur = await self.conn.execute("SELECT * FROM watches WHERE tg_id=?", (tg_id,))
        return list(await cur.fetchall())

    async def update_watch(self, watch_id: int, last_run_id: int | None, last_status: str | None) -> None:
        await self.conn.execute(
            "UPDATE watches SET last_run_id=?, last_status=? WHERE id=?", (last_run_id, last_status, watch_id)
        )

    # ------------------------------------------------------------ ai sessions
    async def create_session(self, session_id: str, tg_id: int, model: str | None, system_prompt: str | None) -> None:
        now = time.time()
        await self.conn.execute(
            "INSERT INTO ai_sessions(id,tg_id,model,system_prompt,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (session_id, tg_id, model, system_prompt, now, now),
        )

    async def get_session(self, session_id: str) -> Optional[aiosqlite.Row]:
        cur = await self.conn.execute("SELECT * FROM ai_sessions WHERE id=?", (session_id,))
        return await cur.fetchone()

    async def update_session(self, session_id: str, **fields: Any) -> None:
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k}=?" for k in fields)
        await self.conn.execute(f"UPDATE ai_sessions SET {cols} WHERE id=?", (*fields.values(), session_id))

    async def list_sessions(self, tg_id: int, limit: int = 10) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM ai_sessions WHERE tg_id=? ORDER BY updated_at DESC LIMIT ?", (tg_id, limit)
        )
        return list(await cur.fetchall())

    async def delete_session(self, session_id: str) -> None:
        await self.conn.execute("DELETE FROM ai_messages_fts WHERE session_id=?", (session_id,))
        await self.conn.execute("DELETE FROM ai_sessions WHERE id=?", (session_id,))

    async def add_message(self, session_id: str, msg: dict) -> int:
        cur = await self.conn.execute(
            "INSERT INTO ai_messages(session_id,role,content,tool_calls,tool_call_id,name,created_at) VALUES(?,?,?,?,?,?,?)",
            (
                session_id,
                msg.get("role"),
                msg.get("content") if isinstance(msg.get("content"), str) else json.dumps(msg.get("content")),
                json.dumps(msg["tool_calls"], ensure_ascii=False) if msg.get("tool_calls") else None,
                msg.get("tool_call_id"),
                msg.get("name"),
                time.time(),
            ),
        )
        mid = cur.lastrowid or 0
        content = msg.get("content")
        if isinstance(content, str) and content and msg.get("role") in ("user", "assistant"):
            await self.conn.execute(
                "INSERT INTO ai_messages_fts(content, session_id, msg_id) VALUES(?,?,?)", (content, session_id, mid)
            )
        await self.conn.execute("UPDATE ai_sessions SET updated_at=? WHERE id=?", (time.time(), session_id))
        return mid

    async def get_messages(self, session_id: str) -> list[dict]:
        cur = await self.conn.execute("SELECT * FROM ai_messages WHERE session_id=? ORDER BY id", (session_id,))
        out = []
        for r in await cur.fetchall():
            m: dict[str, Any] = {"role": r["role"], "content": r["content"]}
            if r["tool_calls"]:
                m["tool_calls"] = json.loads(r["tool_calls"])
            if r["tool_call_id"]:
                m["tool_call_id"] = r["tool_call_id"]
            if r["name"]:
                m["name"] = r["name"]
            out.append(m)
        return out

    async def replace_messages(self, session_id: str, messages: Iterable[dict]) -> None:
        """Used by context compression: rewrite the history atomically."""
        await self.conn.execute("BEGIN")
        try:
            await self.conn.execute("DELETE FROM ai_messages WHERE session_id=?", (session_id,))
            await self.conn.execute("DELETE FROM ai_messages_fts WHERE session_id=?", (session_id,))
            for m in messages:
                await self.add_message(session_id, m)
            await self.conn.execute(
                "UPDATE ai_sessions SET compressions=compressions+1, updated_at=? WHERE id=?", (time.time(), session_id)
            )
            await self.conn.execute("COMMIT")
        except Exception:
            await self.conn.execute("ROLLBACK")
            raise

    async def search_messages(self, tg_id: int, query: str, limit: int = 8) -> list[dict]:
        safe = " ".join(f'"{t}"' for t in query.replace('"', " ").split() if t)
        if not safe:
            return []
        cur = await self.conn.execute(
            """SELECT f.content, f.session_id, s.title, s.updated_at
               FROM ai_messages_fts f JOIN ai_sessions s ON s.id=f.session_id
               WHERE ai_messages_fts MATCH ? AND s.tg_id=? ORDER BY rank LIMIT ?""",
            (safe, tg_id, limit),
        )
        return [dict(r) for r in await cur.fetchall()]

    # ----------------------------------------------------------------- memory
    async def memory_list(self, tg_id: int, target: str) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM ai_memory WHERE tg_id=? AND target=? ORDER BY id", (tg_id, target)
        )
        return list(await cur.fetchall())

    async def memory_add(self, tg_id: int, target: str, content: str) -> None:
        await self.conn.execute(
            "INSERT INTO ai_memory(tg_id,target,content,created_at) VALUES(?,?,?,?)", (tg_id, target, content, time.time())
        )

    async def memory_delete(self, mem_id: int) -> None:
        await self.conn.execute("DELETE FROM ai_memory WHERE id=?", (mem_id,))

    async def memory_update(self, mem_id: int, content: str) -> None:
        await self.conn.execute("UPDATE ai_memory SET content=? WHERE id=?", (content, mem_id))

    # ---------------------------------------------------------------- pending
    async def set_pending(self, tg_id: int, session_id: str, state: dict) -> None:
        await self.conn.execute(
            "INSERT INTO ai_pending(tg_id,session_id,state,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(tg_id) DO UPDATE SET session_id=excluded.session_id, state=excluded.state, updated_at=excluded.updated_at",
            (tg_id, session_id, json.dumps(state, ensure_ascii=False), time.time()),
        )

    async def get_pending(self, tg_id: int) -> Optional[dict]:
        cur = await self.conn.execute("SELECT * FROM ai_pending WHERE tg_id=?", (tg_id,))
        row = await cur.fetchone()
        if not row:
            return None
        return {"session_id": row["session_id"], **json.loads(row["state"])}

    async def all_pending(self) -> list[dict]:
        cur = await self.conn.execute("SELECT * FROM ai_pending")
        return [{"tg_id": r["tg_id"], "session_id": r["session_id"], **json.loads(r["state"])} for r in await cur.fetchall()]

    async def clear_pending(self, tg_id: int) -> None:
        await self.conn.execute("DELETE FROM ai_pending WHERE tg_id=?", (tg_id,))
