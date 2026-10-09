"""Integration harness: drive the real aiogram Dispatcher with synthetic Updates.

* ``FakeSession`` replaces the Bot's HTTP session — every outgoing API call is
  recorded (so tests assert on what the user would see) and answered with a
  plausible object (Message for send/edit, True for the rest).
* ``FakeGitHub`` is an httpx MockTransport implementing the handful of GitHub
  REST endpoints the bot touches, with an in-memory repo store.
* ``Harness`` wires the two together and offers ``text()`` / ``cmd()`` /
  ``tap()`` / ``doc()`` helpers that push Updates through ``dp.feed_update``.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import time
import zipfile
from typing import Any

import httpx
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (AnswerCallbackQuery, DeleteMessage, DeleteWebhook, EditMessageText, GetFile, SendMessage,
                             SetMyCommands, TelegramMethod)
from aiogram.types import (CallbackQuery, Chat, Document, File, Message, Update, User)

from ghbot.core.config import Settings
from ghbot.core.db import Database
from ghbot.github import client as ghclient
from ghbot.telegram.bot import build

USER_ID = 777
CHAT_ID = 777


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self._mid = 1000
        self.files: dict[str, bytes] = {}

    async def close(self):
        pass

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        data = self.files.get(url.rsplit("/", 1)[-1], b"")
        yield data

    async def make_request(self, bot: Bot, method: TelegramMethod, timeout=None):
        self.calls.append(method)
        now = int(time.time())
        if isinstance(method, SendMessage):
            self._mid += 1
            return Message(message_id=self._mid, date=now, chat=Chat(id=method.chat_id, type="private"),
                           from_user=User(id=1, is_bot=True, first_name="bot"), text=method.text,
                           reply_markup=method.reply_markup if hasattr(method.reply_markup, "inline_keyboard") else None).as_(bot)
        if isinstance(method, EditMessageText):
            return Message(message_id=method.message_id, date=now, chat=Chat(id=method.chat_id, type="private"),
                           from_user=User(id=1, is_bot=True, first_name="bot"), text=method.text,
                           reply_markup=method.reply_markup).as_(bot)
        if isinstance(method, GetFile):
            return File(file_id=method.file_id, file_unique_id="u", file_size=len(self.files.get(method.file_id, b"")),
                        file_path=f"documents/{method.file_id}").as_(bot)
        if isinstance(method, (AnswerCallbackQuery, DeleteMessage, DeleteWebhook, SetMyCommands)):
            return True
        return True

    # ---- helpers for assertions
    def sent_texts(self) -> list[str]:
        return [c.text for c in self.calls if isinstance(c, (SendMessage, EditMessageText)) and c.text]

    def last_text(self) -> str:
        texts = self.sent_texts()
        return texts[-1] if texts else ""

    def all_text(self) -> str:
        return "\n---\n".join(self.sent_texts())

    def last_markup(self):
        for c in reversed(self.calls):
            if isinstance(c, (SendMessage, EditMessageText)) and getattr(c.reply_markup, "inline_keyboard", None):
                return c.reply_markup
        return None

    def buttons(self) -> dict[str, str]:
        """text -> callback_data of the most recent inline keyboard."""
        kb = self.last_markup()
        out = {}
        if kb:
            for row in kb.inline_keyboard:
                for b in row:
                    out[b.text] = b.callback_data
        return out

    def find_button(self, substr: str) -> str | None:
        for text, data in self.buttons().items():
            if substr in text or (data and substr in data):
                return data
        return None

    def clear(self):
        self.calls.clear()


class FakeGitHub:
    """Minimal GitHub REST emulation."""

    def __init__(self, scopes="repo, workflow, delete_repo, admin:org, user"):
        self.scopes = scopes
        self.repos: dict[str, dict] = {}
        self.secrets: dict[str, dict[str, str]] = {}
        self.variables: dict[str, dict[str, str]] = {}
        self.trees: dict[str, dict[str, bytes]] = {}
        self.blobs: dict[str, bytes] = {}
        self.workflows: dict[str, list[dict]] = {}
        self.runs: dict[str, list[dict]] = {}
        self.dispatches: list[dict] = []
        self.requests: list[tuple[str, str]] = []
        self.fail_next: tuple[int, str] | None = None
        self.rate_limit_once = False
        self.login = "octo"
        self.add_repo("octo/demo", private=True)
        self.add_repo("octo/site", private=False)

    def add_repo(self, full, private=True):
        owner, name = full.split("/")
        self.repos[full] = {"id": len(self.repos) + 1, "full_name": full, "name": name, "owner": {"login": owner},
                            "private": private, "default_branch": "main", "description": "demo repo",
                            "html_url": f"https://github.com/{full}", "updated_at": "2026-01-01T00:00:00Z",
                            "stargazers_count": 3, "forks_count": 1, "open_issues_count": 0,
                            "has_issues": True, "has_wiki": False, "permissions": {"admin": True, "push": True, "pull": True}}
        self.trees[full] = {"README.md": b"# demo\n", ".github/workflows/ci.yml": b"on: push\nenv:\n  A: ${{ secrets.MY_SECRET }}\n  B: ${{ secrets.OTHER }}\n"}
        self.secrets[full] = {"MY_SECRET": "2026-01-01T00:00:00Z"}
        self.variables[full] = {}
        self.workflows[full] = [{"id": 11, "name": "CI", "path": ".github/workflows/ci.yml", "state": "active"}]
        self.runs[full] = [{"id": 501, "run_number": 7, "name": "CI", "status": "completed", "conclusion": "failure",
                            "head_branch": "main", "event": "push", "updated_at": "2026-01-01T00:00:00Z",
                            "created_at": "2026-01-01T00:00:00Z", "html_url": f"https://github.com/{full}/actions/runs/501"},
                           {"id": 502, "run_number": 8, "name": "CI", "status": "in_progress", "conclusion": None,
                            "head_branch": "main", "event": "push", "updated_at": "2026-01-01T00:00:00Z",
                            "created_at": "2026-01-01T00:00:00Z", "html_url": f"https://github.com/{full}/actions/runs/502"}]

    def _tree_json(self, full):
        return {"sha": "t0", "truncated": False,
                "tree": [{"path": p, "type": "blob", "sha": f"b{i}", "mode": "100644"} for i, p in enumerate(sorted(self.trees[full]))]}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        self.requests.append((method, path))
        hdr = {"X-OAuth-Scopes": self.scopes, "X-RateLimit-Remaining": "4999", "X-RateLimit-Limit": "5000"}
        if self.fail_next:
            status, msg = self.fail_next
            self.fail_next = None
            return httpx.Response(status, json={"message": msg}, headers=hdr)
        if self.rate_limit_once:
            self.rate_limit_once = False
            return httpx.Response(403, json={"message": "API rate limit exceeded"},
                                  headers={**hdr, "Retry-After": "1", "X-RateLimit-Remaining": "0"})
        body = json.loads(request.content) if request.content else {}

        def ok(data=None, status=200):
            if data is None:
                return httpx.Response(204, headers=hdr)
            return httpx.Response(status, json=data, headers=hdr)

        if path == "/user":
            return ok({"login": self.login, "name": "Octo Cat", "plan": {"name": "free"}, "public_repos": 1,
                       "total_private_repos": 1, "followers": 0})
        if path == "/rate_limit":
            return ok({"resources": {"core": {"limit": 5000, "remaining": 4999, "reset": int(time.time()) + 100}}})
        if path == "/user/orgs":
            return ok([])
        if path == "/user/repos" and method == "GET":
            page = int(request.url.params.get("page", "1"))
            return ok(list(self.repos.values()) if page == 1 else [])
        if path == "/user/repos" and method == "POST":
            full = f"{self.login}/{body['name']}"
            if full in self.repos:
                return ok({"message": "Repository creation failed.", "errors": [{"field": "name", "code": "custom", "message": "name already exists on this account"}]}, 422)
            self.add_repo(full, private=body.get("private", True))
            self.repos[full]["description"] = body.get("description", "")
            if not body.get("auto_init", True):
                self.trees[full] = {}
            return ok(self.repos[full], 201)
        parts = path.strip("/").split("/")
        if parts[0] == "repos" and len(parts) >= 3:
            full = f"{parts[1]}/{parts[2]}"
            if full not in self.repos:
                return ok({"message": "Not Found"}, 404)
            rest = parts[3:]
            if not rest:
                if method == "GET":
                    return ok(self.repos[full])
                if method == "PATCH":
                    self.repos[full].update(body)
                    return ok(self.repos[full])
                if method == "DELETE":
                    del self.repos[full]
                    return ok()
            if rest[0] == "git":
                if rest[1] == "trees" and method == "GET":
                    return ok(self._tree_json(full))
                if rest[1] == "ref":
                    return ok({"ref": "refs/heads/main", "object": {"sha": "c0", "type": "commit"}})
                if rest[1] == "commits" and method == "GET":
                    return ok({"sha": "c0", "tree": {"sha": "t0"}})
                if rest[1] == "blobs" and method == "POST":
                    sha = f"blob{len(self.blobs)}"
                    self.blobs[sha] = base64.b64decode(body["content"])
                    return ok({"sha": sha}, 201)
                if rest[1] == "trees" and method == "POST":
                    if "base_tree" not in body:
                        self.trees[full] = {}
                    for item in body["tree"]:
                        self.trees[full][item["path"]] = self.blobs.get(item["sha"], b"")
                    return ok({"sha": "t1"}, 201)
                if rest[1] == "commits" and method == "POST":
                    return ok({"sha": "c1deadbeef00", "html_url": f"https://github.com/{full}/commit/c1deadbeef00"}, 201)
                if rest[1] == "refs":
                    return ok({"ref": "refs/heads/main", "object": {"sha": "c1deadbeef00"}})
            if rest[0] == "contents":
                p = "/".join(rest[1:])
                if method == "GET":
                    if p in self.trees[full]:
                        return ok({"type": "file", "encoding": "base64", "sha": "s", "path": p,
                                   "content": base64.b64encode(self.trees[full][p]).decode()})
                    return ok({"message": "Not Found"}, 404)
                if method == "PUT":
                    self.trees[full][p] = base64.b64decode(body["content"])
                    return ok({"content": {"html_url": f"https://github.com/{full}/blob/main/{p}"}, "commit": {"sha": "c2"}}, 201)
            if rest[0] == "branches":
                return ok([{"name": "main"}])
            if rest[0] == "actions":
                if rest[1] == "secrets":
                    if len(rest) == 2:
                        return ok({"total_count": len(self.secrets[full]),
                                   "secrets": [{"name": n, "updated_at": u} for n, u in self.secrets[full].items()]})
                    if rest[2] == "public-key":
                        from nacl import public, encoding
                        sk = public.PrivateKey.generate()
                        return ok({"key_id": "k1", "key": sk.public_key.encode(encoding.Base64Encoder()).decode()})
                    if method == "PUT":
                        self.secrets[full][rest[2]] = "2026-01-02T00:00:00Z"
                        return ok(None)
                    if method == "DELETE":
                        self.secrets[full].pop(rest[2], None)
                        return ok(None)
                if rest[1] == "variables":
                    if len(rest) == 2 and method == "GET":
                        return ok({"variables": [{"name": n, "value": v} for n, v in self.variables[full].items()]})
                    if method == "POST":
                        if body["name"] in self.variables[full]:
                            return ok({"message": "exists"}, 409)
                        self.variables[full][body["name"]] = body["value"]
                        return ok({}, 201)
                    if method == "PATCH":
                        self.variables[full][rest[2]] = body["value"]
                        return ok(None)
                if rest[1] == "workflows":
                    if len(rest) == 2:
                        return ok({"workflows": self.workflows[full]})
                    if len(rest) == 4 and rest[3] == "dispatches":
                        self.dispatches.append({"repo": full, "wf": rest[2], **body})
                        return ok(None)
                    if len(rest) == 4 and rest[3] == "runs":
                        return ok({"workflow_runs": self.runs[full]})
                if rest[1] == "runs":
                    if len(rest) == 2:
                        st = request.url.params.get("status")
                        runs = [r for r in self.runs[full] if not st or r["status"] == st]
                        return ok({"workflow_runs": runs})
                    rid = int(rest[2])
                    run = next((r for r in self.runs[full] if r["id"] == rid), None)
                    if not run:
                        return ok({"message": "Not Found"}, 404)
                    if len(rest) == 3:
                        return ok(run)
                    if rest[3] == "jobs":
                        return ok({"jobs": [{"id": 9001, "name": "build", "status": run["status"], "conclusion": run["conclusion"], "steps": []}]})
                    if rest[3] == "cancel":
                        run["status"] = "completed"; run["conclusion"] = "cancelled"
                        return ok({}, 202)
                    if rest[3] in ("rerun", "rerun-failed-jobs"):
                        run["status"] = "queued"; run["conclusion"] = None
                        return ok({}, 201)
                if rest[1] == "jobs" and rest[3] == "logs":
                    return httpx.Response(200, text="line1\nline2\nERROR something broke\n", headers=hdr)
            if rest[0] == "issues":
                return ok([])
            if rest[0] == "pulls":
                return ok([])
        return ok({"message": f"unhandled {method} {path}"}, 404)


class Harness:
    def __init__(self, tmp_path, fake_gh: FakeGitHub, env: dict | None = None):
        import os
        os.environ.update({"BOT_TOKEN": "123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "STATE_KEY": "unit-test-state-key-123456",
                           "DATA_DIR": str(tmp_path / "data"), "WORKSPACE_DIR": str(tmp_path / "ws"), **(env or {})})
        self.settings = Settings()
        self.db = Database(self.settings.db_path)
        self.gh = fake_gh
        self.tmp_path = tmp_path
        self._uid = 1
        self._mid = 1

    async def __aenter__(self):
        await self.db.open()
        self.bot, self.dp, self.app = build(self.settings, self.db)
        self.session = FakeSession()
        self.bot._session = self.session
        self.bot.session = self.session
        # patch GitHubClient transport
        orig_init = ghclient.GitHubClient.__init__
        fake = self.gh

        def patched_init(self_, token, **kw):
            orig_init(self_, token, **kw)
            self_._client = httpx.AsyncClient(base_url=ghclient.API, transport=httpx.MockTransport(fake.handler),
                                              headers=self_._client.headers)
        self._orig_init = orig_init
        ghclient.GitHubClient.__init__ = patched_init
        # replace asyncio.sleep in github client with a fast one for rate-limit tests
        return self

    async def __aexit__(self, *exc):
        ghclient.GitHubClient.__init__ = self._orig_init
        for t in list(self.app.ai_tasks.values()):
            if not t.done():
                t.cancel()
        await asyncio.sleep(0)
        await self.db.close()

    # ------------------------------------------------------------ updates
    def _user(self):
        return User(id=USER_ID, is_bot=False, first_name="Tester", username="tester")

    def _chat(self):
        return Chat(id=CHAT_ID, type="private")

    def _message(self, text: str | None = None, document: Document | None = None) -> Message:
        self._mid += 1
        return Message(message_id=self._mid, date=int(time.time()), chat=self._chat(), from_user=self._user(),
                       text=text, document=document)

    async def feed(self, update: Update):
        await self.dp.feed_update(self.bot, update)
        await asyncio.sleep(0)

    async def text(self, text: str):
        self._uid += 1
        await self.feed(Update(update_id=self._uid, message=self._message(text)))

    cmd = text

    async def tap(self, data: str, message_id: int | None = None):
        self._uid += 1
        bot_msg = Message(message_id=message_id or self.session._mid, date=int(time.time()), chat=self._chat(),
                          from_user=User(id=1, is_bot=True, first_name="bot"), text="…")
        cb = CallbackQuery(id=str(self._uid), from_user=self._user(), chat_instance="ci", data=data, message=bot_msg)
        await self.feed(Update(update_id=self._uid, callback_query=cb))

    async def tap_button(self, substr: str):
        data = self.session.find_button(substr)
        assert data, f"no button matching {substr!r} in {list(self.session.buttons())}"
        await self.tap(data)
        return data

    async def doc(self, file_name: str, content: bytes, mime="application/zip"):
        self._uid += 1
        fid = f"file{self._uid}"
        self.session.files[fid] = content
        d = Document(file_id=fid, file_unique_id=f"u{fid}", file_name=file_name, mime_type=mime, file_size=len(content))
        await self.feed(Update(update_id=self._uid, message=self._message(document=d)))

    async def wait_ai(self, timeout=10):
        task = self.app.ai_tasks.get(USER_ID)
        if task:
            await asyncio.wait_for(task, timeout)


def make_zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p, d in files.items():
            zf.writestr(p, d)
    return buf.getvalue()
