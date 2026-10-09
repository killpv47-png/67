"""Workflow restart cycle: checkpoint → handoff/dispatch → fresh run restores DB + skills,
pending AI task resumes, watch loop notifies on run changes."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import httpx
import pytest

from ghbot.ai import llm as llm_mod
from ghbot.core.db import Database
from ghbot.github import client as ghclient
from ghbot.lifecycle import Checkpointer, LifecycleManager
from ghbot.lifecycle.checkpoint import STATE_BRANCH, STATE_PATH
from ghbot.telegram.handlers.ai_chat import resume_pending
from tests.fake_llm import FakeLLM, text_resp, tool_resp
from tests.tg_harness import USER_ID, FakeGitHub, Harness
from tests.test_telegram_flows import TOKEN, onboard

HOST = "octo/ghbot-host"


class HostGitHub(FakeGitHub):
    """FakeGitHub + the host repo where state/state.enc lives on branch ghbot-state."""

    def __init__(self):
        super().__init__()
        self.add_repo(HOST, private=True)
        self.state_blob: bytes | None = None
        self.branches = {HOST: {"main"}}
        self.state_puts = 0

    def handler(self, request):
        path = request.url.path
        if path.startswith(f"/repos/{HOST}/"):
            rest = path[len(f"/repos/{HOST}/"):]
            body = json.loads(request.content) if request.content else {}
            if rest == f"git/ref/heads/{STATE_BRANCH}":
                if STATE_BRANCH in self.branches[HOST]:
                    return httpx.Response(200, json={"object": {"sha": "s0"}})
                return httpx.Response(404, json={"message": "Not Found"})
            if rest == "git/refs" and request.method == "POST":
                self.branches[HOST].add(body["ref"].split("/")[-1])
                return httpx.Response(201, json={})
            if rest == f"contents/{STATE_PATH}":
                if request.method == "GET":
                    if self.state_blob is None:
                        return httpx.Response(404, json={"message": "Not Found"})
                    return httpx.Response(200, json={"type": "file", "encoding": "base64", "sha": "x",
                                                     "content": base64.b64encode(self.state_blob).decode()})
                if request.method == "PUT":
                    assert body.get("branch") == STATE_BRANCH
                    self.state_blob = base64.b64decode(body["content"])
                    self.state_puts += 1
                    return httpx.Response(201, json={"content": {}, "commit": {"sha": "c"}})
        return super().handler(request)


@pytest.fixture
def gh():
    return HostGitHub()


ACTIONS_ENV = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": HOST, "GITHUB_RUN_ID": "4242", "GH_PAT": "ghp_" + "h" * 36,
               "MAX_RUN_MINUTES": "1", "CHECKPOINT_INTERVAL": "1"}


def _patch_llm(monkeypatch, fake: FakeLLM):
    orig_init = llm_mod.LLMClient.__init__

    def patched(self, base_url, api_key, **kw):
        orig_init(self, base_url, api_key, **kw)
        self._client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler), headers=self._client.headers)
    monkeypatch.setattr(llm_mod.LLMClient, "__init__", patched)


async def _lifecycle(h: Harness, home: Path) -> LifecycleManager:
    cp = Checkpointer(h.db, host_repo=h.settings.host_repo, gh_pat=h.settings.gh_pat, state_key=h.settings.state_key, home_dir=home)
    stopped = asyncio.Event()

    async def stop():
        stopped.set()

    async def gh_factory(tg_id):
        return await h.app.gh(tg_id)

    lc = LifecycleManager(h.settings, h.db, h.app.notifier, cp, stop=stop, gh_factory=gh_factory)
    lc.stopped = stopped  # type: ignore[attr-defined]
    h.app.lifecycle = lc
    return lc


async def test_full_restart_cycle_restores_state_and_resumes_ai(tmp_path, gh, monkeypatch):
    home = tmp_path / "home"
    (home / "skills" / "custom" / "my-skill").mkdir(parents=True)
    (home / "skills" / "custom" / "my-skill" / "SKILL.md").write_text("---\nname: my-skill\ndescription: x\n---\nbody")

    # ---------------- RUN 1: onboard, configure AI, start a long AI task, then handoff mid-task
    fake1 = FakeLLM([tool_resp("terminal", {"command": "echo step1"})])  # script ends -> next call would IndexError
    _patch_llm(monkeypatch, fake1)
    async with Harness(tmp_path / "run1", gh, env=ACTIONS_ENV) as h:
        lc = await _lifecycle(h, home)
        assert lc.cp.enabled
        assert await lc.cp.restore_if_needed() in ("fresh", "skipped")
        await onboard(h)
        await h.app.save_ai_config(USER_ID, "https://x/v1", "sk-key-1234567890", "m1")
        await lc.start("fresh")
        assert "Run" in h.session.all_text() or "4242" in h.session.all_text()

        # kick an AI task whose second LLM call blocks (simulate provider slowness) so handoff interrupts it
        gate = asyncio.Event()
        orig_handler = fake1.handler

        def blocking_handler(request):
            if not fake1.script:  # second chat call
                raise httpx.ConnectError("provider down")
            return orig_handler(request)
        fake1.handler = blocking_handler
        h.session.clear()
        await h.text("run echo step1 then tell me")
        await asyncio.sleep(0.3)
        assert "terminal" in h.session.all_text()
        pending = await h.db.get_pending(USER_ID)
        assert pending and pending["phase"] in ("llm", "tools")
        sid = pending["session_id"]

        # handoff (what happens at MAX_RUN_MINUTES or /restart)
        h.session.clear()
        ok = await lc.handoff(reason="budget")
        assert ok is True
        assert gh.dispatches[-1]["repo"] == HOST and gh.dispatches[-1]["wf"] == "bot.yml"
        assert gh.dispatches[-1]["inputs"] == {"reason": "handoff"}
        assert gh.state_blob is not None and len(gh.state_blob) > 100
        assert lc.stopped.is_set()
        assert "run" in h.session.all_text().lower()  # bye notification
        # the encrypted blob never contains plaintext secrets
        assert TOKEN.encode() not in gh.state_blob and b"sk-key-1234567890" not in gh.state_blob
        await lc.shutdown()
        for t in h.app.ai_tasks.values():
            t.cancel()
        await asyncio.sleep(0)

    # ---------------- RUN 2: fresh runner, empty data dir, skills dir wiped → restore from host repo
    import shutil
    shutil.rmtree(home / "skills")
    fake2 = FakeLLM([text_resp("step1 printed OK")])
    _patch_llm(monkeypatch, fake2)
    async with Harness(tmp_path / "run2", gh, env=ACTIONS_ENV) as h2:
        # restore must happen BEFORE db.open(); Harness opened it already, so emulate main.py order
        await h2.db.close()
        h2.db.path.unlink(missing_ok=True)
        lc2 = await _lifecycle(h2, home)
        assert await lc2.cp.restore_if_needed() == "restored"
        await h2.db.open()
        # user, token, language, AI config, sessions all survived
        u = await h2.db.get_user(USER_ID)
        assert u and u["gh_login"] == "octo" and u["access_level"] == "GOD"
        assert await h2.app.token_for(USER_ID) == TOKEN
        assert (await h2.app.ai_config(USER_ID))["model"] == "m1"
        assert (home / "skills" / "custom" / "my-skill" / "SKILL.md").read_text().endswith("body")
        assert await h2.db.get_pending(USER_ID)
        msgs_before = await h2.db.get_messages(sid)
        assert msgs_before[-1]["role"] == "tool"  # tool result persisted before interruption

        await lc2.start("restored")
        await resume_pending(h2.app)
        await h2.wait_ai()
        txt = h2.session.all_text()
        assert "restored" in txt.lower() or "resum" in txt.lower()
        assert "step1 printed OK" in txt
        assert await h2.db.get_pending(USER_ID) is None
        # the resumed request carried the full history (system + user + assistant tool_call + tool result)
        roles = [m["role"] for m in fake2.requests[0]["messages"]]
        assert roles == ["system", "user", "assistant", "tool"]
        await lc2.shutdown()


async def test_checkpoint_skips_unchanged_and_wrong_key(tmp_path, gh):
    home = tmp_path / "home"
    home.mkdir()
    async with Harness(tmp_path / "r", gh, env=ACTIONS_ENV) as h:
        lc = await _lifecycle(h, home)
        await onboard(h)
        assert await lc.cp.save() is True
        assert await lc.cp.save() is False          # unchanged → no push
        assert await lc.cp.save(force=True) is True
        assert gh.state_puts == 2
    # a different STATE_KEY must not crash — start fresh, keep the old blob
    async with Harness(tmp_path / "r2", gh, env={**ACTIONS_ENV, "STATE_KEY": "another-key-that-is-long-enough"}) as h2:
        await h2.db.close()
        h2.db.path.unlink(missing_ok=True)
        lc2 = await _lifecycle(h2, home)
        assert await lc2.cp.restore_if_needed() == "failed"
        await h2.db.open()
        assert await h2.db.get_user(USER_ID) is None


async def test_watch_loop_notifies_on_run_change(tmp_path, gh):
    home = tmp_path / "home"
    home.mkdir()
    async with Harness(tmp_path / "r", gh) as h:
        lc = await _lifecycle(h, home)
        await onboard(h)
        await h.db.add_watch(USER_ID, "octo/demo")
        await lc.poll_watches()          # baseline
        h.session.clear()
        await lc.poll_watches()
        assert h.session.all_text() == ""  # nothing changed
        gh.runs["octo/demo"].insert(0, {"id": 503, "run_number": 9, "name": "CI", "status": "completed", "conclusion": "success",
                                        "head_branch": "main", "event": "push", "updated_at": "2026-01-03T00:00:00Z",
                                        "created_at": "2026-01-03T00:00:00Z", "html_url": "https://github.com/octo/demo/actions/runs/503"})
        await lc.poll_watches()
        txt = h.session.all_text()
        assert "✅" in txt and "octo/demo" in txt and "success" in txt
        # repo deleted → watch poll must not crash
        del gh.repos["octo/demo"]
        await lc.poll_watches()


async def test_handoff_without_pat_locally_is_safe(tmp_path, gh):
    home = tmp_path / "home"
    home.mkdir()
    async with Harness(tmp_path / "r", gh, env={"GITHUB_ACTIONS": "", "GH_PAT": "", "GITHUB_REPOSITORY": ""}) as h:
        lc = await _lifecycle(h, home)
        assert not lc.cp.enabled
        await onboard(h)
        ok = await lc.handoff(reason="manual")
        assert ok is False and lc.stopped.is_set()
        assert await lc.handoff() is False  # idempotent


async def test_main_entry_validates_settings(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "")
    monkeypatch.setenv("STATE_KEY", "short")
    from ghbot.core.config import Settings
    s = Settings()
    probs = s.validate()
    assert any("BOT_TOKEN" in p for p in probs) and any("STATE_KEY" in p for p in probs)


async def test_resume_repairs_partial_tool_results(tmp_path, gh, monkeypatch):
    """Interrupted mid-tools: 2 calls issued, only 1 result stored → the orphaned assistant turn is dropped
    so the resumed request is valid, and the model re-issues the calls."""
    fake = FakeLLM([text_resp("recovered")])
    _patch_llm(monkeypatch, fake)
    async with Harness(tmp_path / "r", gh) as h:
        await onboard(h)
        await h.app.save_ai_config(USER_ID, "https://x/v1", "sk-key-1234567890", "m1")
        sid = "sess1"
        await h.db.create_session(sid, USER_ID, "m1", None)
        await h.db.kv_set(f"active_session:{USER_ID}", sid)
        await h.db.add_message(sid, {"role": "user", "content": "do two things"})
        await h.db.add_message(sid, {"role": "assistant", "content": "", "tool_calls": [
            {"id": "a", "type": "function", "function": {"name": "terminal", "arguments": "{\"command\":\"echo 1\"}"}},
            {"id": "b", "type": "function", "function": {"name": "terminal", "arguments": "{\"command\":\"echo 2\"}"}}]})
        await h.db.add_message(sid, {"role": "tool", "tool_call_id": "a", "name": "terminal", "content": "{\"output\":\"1\"}"})
        await h.db.set_pending(USER_ID, sid, {"phase": "tools", "iteration": 1})
        await resume_pending(h.app)
        await h.wait_ai()
        roles = [m["role"] for m in fake.requests[0]["messages"]]
        assert roles == ["system", "user"]
        assert "recovered" in h.session.all_text()
        assert await h.db.get_pending(USER_ID) is None
