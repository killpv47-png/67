import asyncio
from pathlib import Path

import pytest

from ghbot.ai import prompt_builder, skills
from ghbot.ai.agent import Agent, AgentConfig
from ghbot.ai.compressor import SUMMARY_PREFIX, ContextCompressor
from ghbot.ai.llm import LLMError, classify

from .fake_llm import FakeLLM, make_client, text_resp, tool_resp


def test_classify():
    assert classify(429, "") == "rate_limit"
    assert classify(401, "") == "auth"
    assert classify(400, "This model's maximum context length is 8192 tokens") == "context_length"
    assert classify(503, "") == "server_error"
    assert classify(400, "Resource exhausted") == "rate_limit"
    assert classify(400, "bad") == "bad_request"


async def test_llm_rate_limit_waits_and_resumes_same_request():
    waits = []

    async def on_wait(secs, kind, attempt):
        waits.append((kind, attempt))

    fake = FakeLLM([(429, {"error": "rate"}, {"retry-after": "0"}), (503, {"error": "down"}, {}), text_resp("ok")])
    client = make_client(fake, on_wait=on_wait)
    client.max_retry_seconds = 60
    r = await client.chat(model="m", messages=[{"role": "user", "content": "hi"}])
    assert r.content == "ok"
    assert len(fake.requests) == 3 and fake.requests[0] == fake.requests[2]
    assert [k for k, _ in waits] == ["rate_limit", "server_error"]


async def test_llm_exhausted_auth_models():
    fake = FakeLLM([(429, {}, {"retry-after": "100"})])
    client = make_client(fake, max_retry_minutes=0.01)
    with pytest.raises(LLMError) as e:
        await client.chat(model="m", messages=[])
    assert e.value.kind == "exhausted"
    with pytest.raises(LLMError) as e:
        await make_client(FakeLLM([(401, {"error": "bad key"}, {})])).chat(model="m", messages=[])
    assert e.value.kind == "auth"
    assert await make_client(FakeLLM([])).list_models() == ["m1", "m2"]


async def _agent(db, tmp_path, fake, **cfg):
    events = []

    async def ev(kind, data):
        events.append((kind, data))

    a = Agent(db=db, tg_id=7, cfg=AgentConfig(base_url="https://fake/v1", api_key="sk-x", model="m", **cfg),
              gh=None, workspace=tmp_path / "ws", events=ev, github_login="alice", access_level="GOD")
    a._llm = make_client(fake, on_wait=a._on_wait)
    return a, events


async def test_agent_tool_loop_and_persistence(db, tmp_path):
    await db.upsert_user(7)
    fake = FakeLLM([
        tool_resp("write_file", {"path": "a.txt", "content": "hello"}),
        tool_resp("read_file", {"path": "a.txt"}, "c2"),
        text_resp("done: file says hello"),
    ])
    agent, events = await _agent(db, tmp_path, fake)
    res = await agent.run("make a file")
    assert res.text.startswith("done") and res.tool_calls == 2 and res.iterations == 3
    assert (tmp_path / "ws" / "a.txt").read_text() == "hello"
    msgs = await db.get_messages(agent.session_id)
    assert [m["role"] for m in msgs] == ["user", "assistant", "tool", "assistant", "tool", "assistant"]
    assert await db.get_pending(7) is None
    kinds = [k for k, _ in events]
    assert "tool_call" in kinds and "tool_result" in kinds and "thinking" in kinds
    sp = (await db.get_session(agent.session_id))["system_prompt"]
    assert "GITHUB_AI" in sp and "AGENTS.md" in sp and "<available_skills>" in sp and "@alice" in sp
    assert fake.requests[0]["messages"][0]["content"] == sp
    names = {t["function"]["name"] for t in fake.requests[0]["tools"]}
    assert "terminal" in names and "web_search" not in names


async def test_agent_rate_limit_inside_loop_emits_event(db, tmp_path):
    await db.upsert_user(7)
    fake = FakeLLM([(429, {}, {"retry-after": "0"}), text_resp("fine")])
    agent, events = await _agent(db, tmp_path, fake)
    assert (await agent.run("x")).text == "fine"
    assert ("rate_limited", {"secs": 0, "attempt": 1, "kind": "rate_limit"}) in events


async def test_agent_exhausted_keeps_pending_then_resumes(db, tmp_path):
    await db.upsert_user(7)
    fake = FakeLLM([(429, {}, {"retry-after": "100"})])
    agent, _ = await _agent(db, tmp_path, fake)
    agent._llm.max_retry_seconds = 1
    res = await agent.run("x")
    assert res.error and "exhausted" in res.error
    assert (await db.get_pending(7))["phase"] == "llm"
    fake.script = [text_resp("resumed")]
    assert (await agent.run(None, resume=True)).text == "resumed"
    assert len([m for m in await db.get_messages(agent.session_id) if m["role"] == "user"]) == 1


async def test_agent_context_length_forces_compression(db, tmp_path):
    await db.upsert_user(7)
    fake = FakeLLM([
        (400, {"error": {"message": "maximum context length exceeded"}}, {}),
        text_resp("## Historical Task Snapshot\nNone\n## Goal\nG"),
        text_resp("after compaction"),
    ])
    agent, events = await _agent(db, tmp_path, fake)
    await agent._ensure()
    for i in range(6):
        await db.add_message(agent.session_id, {"role": "user", "content": f"q{i}"})
        await db.add_message(agent.session_id, {"role": "assistant", "content": f"a{i}"})
    res = await agent.run("now")
    assert res.text == "after compaction"
    assert "compressing" in [k for k, _ in events]
    msgs = await db.get_messages(agent.session_id)
    assert any(isinstance(m.get("content"), str) and m["content"].startswith(SUMMARY_PREFIX) for m in msgs)


async def test_agent_cancel(db, tmp_path):
    await db.upsert_user(7)
    agent, _ = await _agent(db, tmp_path, FakeLLM([(429, {}, {"retry-after": "30"})]))
    task = asyncio.create_task(agent.run("x"))
    await asyncio.sleep(0.3)
    agent.cancel.set()
    assert (await task).stopped


async def test_agent_empty_response_guard(db, tmp_path):
    await db.upsert_user(7)
    agent, _ = await _agent(db, tmp_path, FakeLLM([text_resp(""), text_resp("real answer")]))
    assert (await agent.run("hi")).text == "real answer"


async def test_compressor_prune_then_summarize():
    fake = FakeLLM([text_resp("## Historical Task Snapshot\nNone\n## Goal\nG")])
    c = ContextCompressor(make_client(fake), "m", context_length=2000, threshold=0.5, protect_last_turns=2, tool_prune_chars=100)
    msgs = [{"role": "user", "content": "start"}]
    for i in range(10):
        msgs.append({"role": "assistant", "content": None, "tool_calls": [{"id": f"c{i}", "type": "function", "function": {"name": "terminal", "arguments": "{}"}}]})
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "name": "terminal", "content": "x" * 500 + " sk-secretsecretsecretsecret"})
        msgs.append({"role": "assistant", "content": f"step {i} done"})
        msgs.append({"role": "user", "content": f"next {i}"})
    assert c.needs_compression("sys", msgs)
    new, changed = await c.compress("sys", msgs)
    assert changed and new[0] == msgs[0] and new[2]["content"].startswith(SUMMARY_PREFIX) and new[-1] == msgs[-1]
    assert len(new) < len(msgs)
    roles = [m["role"] for m in new if m["role"] != "tool"]
    assert all(a != b for a, b in zip(roles, roles[1:]))
    assert "sk-secret" not in fake.requests[0]["messages"][0]["content"]


async def test_compressor_mechanical_fallback_on_error():
    c = ContextCompressor(make_client(FakeLLM([(401, {}, {})])), "m", context_length=500, protect_last_turns=1)
    msgs = [{"role": "user", "content": "a" * 300}] + [{"role": "assistant", "content": "b" * 300}, {"role": "user", "content": "c" * 300}] * 3
    new, changed = await c.compress("", msgs, force=True)
    assert changed and "Completed Actions" in new[2]["content"]


def test_bundled_skills_and_prompt_tiers():
    names = {s["name"] for s in skills.catalog()}
    assert {"repo-upload", "actions-debugging", "secrets-management", "bot-self-maintenance"} <= names
    p = prompt_builder.build_system_prompt(model="m", session_id="s", skills_index=skills.skills_index_block(),
                                           memory_block="## Persistent Memory\n- x", user_block="", workspace=Path("/tmp/ws"),
                                           in_actions=True, host_repo="o/r", run_id="1", has_web_search=True,
                                           github_login="u", access_level="GOD")
    i = [p.index(x) for x in ("GITHUB_AI, the resident", "# Project Context", "<available_skills>",
                              "## Persistent Memory", "# GITHUB_AI runtime environment")]
    assert i == sorted(i)
    assert "web_search + web_extract" in p and "GH_PAT" in p and "run_id=1" in p
