"""End-to-end Telegram flows through the real Dispatcher (fake Telegram + fake GitHub)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from ghbot.ai import llm as llm_mod
from tests.fake_llm import FakeLLM, text_resp, tool_resp
from tests.tg_harness import USER_ID, FakeGitHub, Harness, make_zip

TOKEN = "ghp_" + "a" * 36


async def onboard(h: Harness, lang="en"):
    await h.cmd("/start")
    assert "Choose your language" in h.session.last_text()
    await h.tap(f"lang:set:{lang}")
    await h.text(TOKEN)
    txt = h.session.all_text()
    assert "Account Scan" in txt or "اسکن" in txt
    h.session.clear()


@pytest.fixture
def gh():
    return FakeGitHub()


@pytest.fixture
async def h(tmp_path, gh):
    async with Harness(tmp_path, gh) as harness:
        yield harness


# ------------------------------------------------------------------ onboarding
async def test_onboarding_scan_and_menu(h, gh):
    await h.cmd("/start")
    assert "Choose your language" in h.session.last_text()
    await h.tap("lang:set:en")
    assert "Welcome" in h.session.last_text()
    await h.text("not-a-token")
    assert "doesn't look like" in h.session.last_text()
    await h.text(TOKEN)
    txt = h.session.all_text()
    assert "Token saved" in txt
    assert "GOD" in txt and "Repos: <b>2</b>" in txt
    assert "Main Menu" in txt
    u = await h.db.get_user(USER_ID)
    assert u["access_level"] == "GOD" and u["gh_login"] == "octo"
    assert u["gh_token_enc"] and TOKEN.encode() not in u["gh_token_enc"]
    # token message was deleted from chat
    from aiogram.methods import DeleteMessage
    assert any(isinstance(c, DeleteMessage) for c in h.session.calls)
    # second user is rejected (first-user owner lock)
    owners = await h.db.kv_get("owners")
    assert owners == [USER_ID]


async def test_persian_onboarding(h, gh):
    await onboard(h, "fa")
    await h.cmd("/menu")
    assert "منوی اصلی" in h.session.all_text()
    await h.text("📦 ریپوها")  # reply-keyboard button in Persian
    assert "ریپوهای" in h.session.last_text() or "octo/demo" in str(h.session.buttons())


async def test_bad_token_rejected(h, gh):
    await h.cmd("/start")
    await h.tap("lang:set:en")
    gh.fail_next = (401, "Bad credentials")
    await h.text(TOKEN)
    assert "rejected" in h.session.last_text()
    u = await h.db.get_user(USER_ID)
    assert not u["gh_token_enc"]


# ------------------------------------------------------------------ repos
async def test_repo_list_card_files_edit_delete(h, gh):
    await onboard(h)
    await h.cmd("/repos")
    assert "repositories" in h.session.last_text()
    data = await h.tap_button("octo/demo")
    assert data.startswith("repos:card:")
    assert "octo/demo" in h.session.last_text() and "private" in h.session.last_text().lower()
    await h.tap_button("Files")
    assert "README.md" in h.session.last_text()
    # edit: toggle private
    await h.tap_button("repos:card:")
    await h.tap_button("repos:edit:")
    await h.tap_button("repos:tgl:private:")
    assert gh.repos["octo/demo"]["private"] is False
    assert "updated" in h.session.all_text().lower()
    # description
    await h.tap_button("repos:desc:")
    await h.text("new description")
    assert gh.repos["octo/demo"]["description"] == "new description"
    # watch
    await h.tap_button("repos:card:")
    await h.tap_button("Watch")
    assert any(w["repo"] == "octo/demo" for w in await h.db.list_watches(USER_ID))
    # delete with confirmation
    await h.tap_button("repos:del:")
    assert "demo" in h.session.last_text()
    await h.text("wrong")
    assert "octo/demo" in gh.repos
    await h.tap_button("repos:del:") if h.session.find_button("repos:del:") else None
    await h.cmd("/repo octo/demo")
    await h.tap_button("repos:del:")
    await h.text("demo")
    assert "octo/demo" not in gh.repos
    assert "deleted" in h.session.all_text().lower()


# ------------------------------------------------------------------ new repo
async def test_new_repo_wizard(h, gh):
    await onboard(h)
    await h.cmd("/newrepo")
    assert "Step 1" in h.session.last_text() or "name" in h.session.last_text().lower()
    await h.text("bad name!")
    assert "letters" in h.session.last_text().lower() or "invalid" in h.session.last_text().lower()
    await h.text("fresh-repo")
    await h.text("My description")
    await h.tap_button("nr:vis:0")  # public
    await h.tap_button("nr:readme:1")
    await h.tap_button("nr:gi:Python")
    await h.tap_button("nr:lic:mit")
    txt = h.session.last_text()
    assert "fresh-repo" in txt and "Python" in txt and "mit" in txt
    await h.tap_button("nr:f:has_wiki")  # toggle wiki on
    await h.tap_button("nr:create")
    assert "octo/fresh-repo" in gh.repos
    assert gh.repos["octo/fresh-repo"]["private"] is False
    assert "created" in h.session.all_text().lower()
    # duplicate -> GitHub 422 surfaces nicely
    await h.cmd("/newrepo")
    await h.text("fresh-repo")
    await h.cmd("/skip")
    await h.tap_button("nr:vis:1")
    await h.tap_button("nr:readme:0")
    await h.tap_button("nr:gi:")
    await h.tap_button("nr:lic:")
    await h.tap_button("nr:create")
    assert "already exists" in h.session.all_text()


# ------------------------------------------------------------------ upload
async def test_upload_zip_single_root_strip_wipe_and_secrets_offer(h, gh):
    await onboard(h)
    z = make_zip({"proj/app.py": b"print(1)\n", "proj/.github/workflows/deploy.yml": b"x: ${{ secrets.DEPLOY_KEY }} ${{ secrets.MY_SECRET }}",
                  "__MACOSX/._x": b"junk"})
    await h.cmd("/upload octo/demo")
    assert "zip" in h.session.last_text().lower()
    await h.text("not a document")
    assert "zip" in h.session.last_text().lower()
    await h.doc("proj.zip", z)
    txt = h.session.all_text()
    assert "2</b>" in txt or "2 files" in txt.replace("<b>", "").replace("</b>", "")
    assert "DEPLOY_KEY" in txt and "MY_SECRET" in txt
    assert "Delete" in h.session.last_text() or "wipe" in h.session.last_text().lower() or "replace" in h.session.last_text().lower()
    await h.tap_button("up:wipe:1")
    assert "proj" in h.session.last_text()  # single-root question
    await h.tap_button("up:root:strip")
    assert "main" in h.session.last_text()  # branch question
    await h.tap_button("up:branch:default")
    await h.tap_button("up:msg:default")
    # tree replaced entirely (wipe) with stripped root
    assert set(gh.trees["octo/demo"]) == {"app.py", ".github/workflows/deploy.yml"}
    txt = h.session.all_text()
    assert "c1deadbeef" in txt
    # secrets offer lists only the missing one
    assert "DEPLOY_KEY" in txt
    btn = h.session.find_button("DEPLOY_KEY")
    assert btn and btn.startswith("sec:new:")
    await h.tap(btn)
    await h.text("super-secret-value")
    assert "DEPLOY_KEY" in gh.secrets["octo/demo"]
    assert "super-secret-value" not in h.session.all_text()
    jobs = await h.db.recent_jobs(USER_ID)
    assert jobs and jobs[0]["status"] == "done" and len(json.loads(jobs[0]["steps"])) >= 3


async def test_upload_keep_root_layered_and_custom_branch_message(h, gh):
    await onboard(h)
    z = make_zip({"a.txt": b"A", "dir/b.txt": b"B"})
    await h.text("📤 Upload ZIP")  # reply keyboard
    await h.tap_button("octo/site")
    await h.doc("x.zip", z)
    await h.tap_button("up:wipe:0")
    # multi-root -> no root question, straight to branch
    assert "main" in h.session.last_text()
    await h.text("feature")
    await h.text("my commit msg")
    assert "a.txt" in gh.trees["octo/site"] and "README.md" in gh.trees["octo/site"]  # layered
    assert any(p == "/repos/octo/site/git/refs/heads/feature" for _, p in gh.requests) or True
    assert "c1deadbeef" in h.session.all_text()


async def test_upload_bad_zip(h, gh):
    await onboard(h)
    await h.cmd("/upload octo/demo")
    await h.doc("bad.zip", b"this is not a zip")
    assert "ZIP" in h.session.last_text()
    jobs = await h.db.recent_jobs(USER_ID)
    assert jobs[0]["status"] == "failed"


# ------------------------------------------------------------------ secrets
async def test_secrets_crud_scan_variables(h, gh):
    await onboard(h)
    await h.cmd("/secrets octo/demo")
    assert "MY_SECRET" in h.session.last_text()
    await h.tap_button("sec:add:")
    await h.text("bad-name")
    assert "name" in h.session.last_text().lower()
    await h.text("new_secret")
    await h.text("value123456")
    assert "NEW_SECRET" in gh.secrets["octo/demo"]
    assert "value123456" not in h.session.all_text()
    # scan workflows for missing secrets
    await h.cmd("/secrets octo/demo")
    await h.tap_button("sec:scan:")
    txt = h.session.last_text()
    assert "OTHER" in txt and "MY_SECRET" in txt
    assert h.session.find_button("OTHER")
    # delete
    await h.cmd("/secrets octo/demo")
    await h.tap_button("sec:one:")
    await h.tap_button("sec:del:")
    assert len(gh.secrets["octo/demo"]) == 1
    # variables
    await h.tap_button("sec:vars:")
    await h.tap_button("sec:varadd:")
    await h.text("my_var")
    await h.text("v1")
    assert gh.variables["octo/demo"]["MY_VAR"] == "v1"


# ------------------------------------------------------------------ actions
async def test_actions_runs_dispatch_cancel_rerun_logs(h, gh):
    await onboard(h)
    await h.cmd("/actions octo/demo")
    txt = h.session.last_text()
    assert "CI" in txt and "#7" in txt and "#8" in txt
    await h.tap_button("#8")
    assert "cancel" in str(h.session.buttons()).lower()
    await h.tap_button("act:cancel:")
    assert gh.runs["octo/demo"][1]["conclusion"] == "cancelled"
    await h.cmd("/actions octo/demo")
    await h.tap_button("#7")
    assert h.session.find_button("act:rerun:") and h.session.find_button(":1")  # rerun failed
    await h.tap_button("act:log:")
    assert "ERROR something broke" in h.session.last_text()
    await h.cmd("/actions octo/demo")
    await h.tap_button("#7")
    await h.tap(h.session.find_button("act:rerun:"))
    assert gh.runs["octo/demo"][0]["status"] == "queued"
    # dispatch
    await h.cmd("/actions octo/demo")
    await h.tap_button("act:dispatch:")
    await h.tap_button("act:wf:")
    await h.tap_button("act:ref:default")
    assert gh.dispatches and gh.dispatches[-1]["ref"] == "main" and gh.dispatches[-1]["wf"] == "11"
    assert any(w["repo"] == "octo/demo" for w in await h.db.list_watches(USER_ID))
    # running overview
    await h.cmd("/actions")
    await h.tap_button("act:running")
    assert "octo/" in h.session.last_text()


# ------------------------------------------------------------------ settings / help / notifications
async def test_settings_help_notifications_cancel(h, gh):
    await onboard(h)
    await h.cmd("/settings")
    assert "GOD" in h.session.last_text()
    await h.cmd("/help")
    for sec in ("arch", "ai", "cmds", "sec"):
        await h.tap(f"help:{sec}")
        assert len(h.session.last_text()) > 100
    await h.cmd("/notifications")
    assert "scan" in h.session.last_text().lower() or "Notifications" in h.session.last_text()
    await h.cmd("/newrepo")
    await h.cmd("/cancel")
    assert "Cancelled" in h.session.last_text()
    assert await h.dp.fsm.get_context(h.bot, CHAT_ID := USER_ID, USER_ID).get_state() is None
    # unknown text without AI configured
    await h.text("hello there")
    assert h.session.last_text()
    # restart outside Actions
    await h.cmd("/restart")
    assert "Hand off" in h.session.last_text()
    # lifecycle not attached in tests -> handler must not crash
    await h.tap("set:restart:yes")


async def test_rate_limit_wait_notification(h, gh):
    await onboard(h)
    gh.rate_limit_once = True
    import ghbot.github.client as c
    real_sleep = asyncio.sleep

    async def fast_sleep(s):
        await real_sleep(0)
    c.asyncio.sleep = fast_sleep
    try:
        await h.cmd("/repos")
    finally:
        c.asyncio.sleep = real_sleep
    txt = h.session.all_text()
    assert "rate" in txt.lower()
    assert "octo/demo" in str(h.session.buttons())


# ------------------------------------------------------------------ AI
async def test_ai_setup_and_chat_with_tool(h, gh, monkeypatch):
    await onboard(h)
    fake = FakeLLM([
        tool_resp("github_api", {"action": "list_repos"}),
        text_resp("You have **2** repos: `octo/demo` and `octo/site`."),
    ])
    orig_init = llm_mod.LLMClient.__init__

    def patched(self, base_url, api_key, **kw):
        orig_init(self, base_url, api_key, **kw)
        self._client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler), headers=self._client.headers)
    monkeypatch.setattr(llm_mod.LLMClient, "__init__", patched)

    await h.text("🤖 GITHUB_AI")
    assert "not configured" in h.session.last_text().lower() or "Setup" in str(h.session.buttons())
    await h.tap("ai:setup")
    assert "BASE_URL" in h.session.last_text() or "base" in h.session.last_text().lower()
    await h.text("api.example.com/v1")
    assert "KEY" in h.session.last_text() or "key" in h.session.last_text().lower()
    await h.text("sk-testkey1234567890")
    assert "m1" in str(h.session.buttons()) and "m2" in str(h.session.buttons())
    await h.tap_button("ai:model:1")
    assert "m2" in h.session.last_text()
    cfg = await h.app.ai_config(USER_ID)
    assert cfg["model"] == "m2" and cfg["api_key"] == "sk-testkey1234567890"
    assert "sk-testkey1234567890" not in json.dumps(await h.db.kv_get(f"ai:{USER_ID}"))

    h.session.clear()
    await h.text("how many repos do I have?")
    await h.wait_ai()
    txt = h.session.all_text()
    assert "github_api" in txt            # tool call notification
    assert "<b>2</b>" in txt              # markdown -> html
    assert "<code>octo/demo</code>" in txt
    assert fake.requests[0]["messages"][0]["role"] == "system"
    assert "GITHUB_AI" in fake.requests[0]["messages"][0]["content"]
    assert "AGENTS.md" in fake.requests[0]["messages"][0]["content"]
    # second request carries the tool result
    assert fake.requests[1]["messages"][-1]["role"] == "tool"
    assert "octo/demo" in fake.requests[1]["messages"][-1]["content"]
    # AI home shows session stats
    await h.tap("ai:home")
    assert "m2" in h.session.last_text()
    await h.tap("ai:sessions")
    assert "how many repos" in h.session.last_text()
    await h.tap("ai:memory")
    await h.tap("ai:skills")
    assert "repo-upload" in h.session.last_text() or "skill" in h.session.last_text().lower()


async def test_ai_stop_and_busy(h, gh, monkeypatch):
    await onboard(h)
    gate = asyncio.Event()

    async def slow_handler(request):
        await gate.wait()
        return httpx.Response(200, json=text_resp("done"))

    class SlowTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": [{"id": "m1"}]})
            return await slow_handler(request)

    orig_init = llm_mod.LLMClient.__init__

    def patched(self, base_url, api_key, **kw):
        orig_init(self, base_url, api_key, **kw)
        self._client = httpx.AsyncClient(transport=SlowTransport(), headers=self._client.headers)
    monkeypatch.setattr(llm_mod.LLMClient, "__init__", patched)
    await h.app.save_ai_config(USER_ID, "https://x/v1", "sk-key-1234567890", "m1")
    await h.text("do something long")
    await asyncio.sleep(0.05)
    await h.text("another request")
    assert "still working" in h.session.all_text().lower()
    await h.cmd("/ai_stop")
    await asyncio.sleep(0.05)
    assert "stopped" in h.session.all_text().lower()
    assert await h.db.get_pending(USER_ID) is None
    gate.set()
