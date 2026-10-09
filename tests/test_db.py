import pytest


async def test_users_kv_notifications(db):
    u = await db.upsert_user(1, "alice")
    assert u["lang"] == "en"
    await db.set_user_fields(1, lang="fa", access_level="GOD")
    assert (await db.get_user(1))["lang"] == "fa"
    await db.kv_set("k", {"a": 1})
    assert await db.kv_get("k") == {"a": 1}
    assert await db.kv_get("missing", 5) == 5
    for i in range(3):
        await db.add_notification(1, "x", f"n{i}")
    rows = await db.recent_notifications(1, 2)
    assert [r["text"] for r in rows] == ["n2", "n1"]


async def test_jobs_and_watches(db):
    await db.upsert_user(1)
    await db.create_job("j1", 1, "upload", "title")
    await db.job_step("j1", "step one")
    await db.job_step("j1", "step two", ok=False)
    await db.finish_job("j1", "failed")
    j = await db.get_job("j1")
    assert j["status"] == "failed"
    import json
    assert len(json.loads(j["steps"])) == 2
    await db.add_watch(1, "o/r")
    await db.add_watch(1, "o/r")  # idempotent
    assert len(await db.list_watches(1)) == 1
    w = (await db.list_watches())[0]
    await db.update_watch(w["id"], 42, "42:completed:success")
    assert (await db.list_watches(1))[0]["last_run_id"] == 42
    await db.remove_watch(1, "o/r")
    assert await db.list_watches(1) == []


async def test_sessions_messages_fts_and_replace(db):
    await db.upsert_user(1)
    await db.create_session("s1", 1, "m", "sys")
    await db.add_message("s1", {"role": "user", "content": "deploy the kubernetes cluster"})
    await db.add_message("s1", {"role": "assistant", "content": "ok", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "terminal", "arguments": "{}"}}]})
    await db.add_message("s1", {"role": "tool", "tool_call_id": "c1", "name": "terminal", "content": "done"})
    msgs = await db.get_messages("s1")
    assert [m["role"] for m in msgs] == ["user", "assistant", "tool"]
    assert msgs[1]["tool_calls"][0]["function"]["name"] == "terminal"
    hits = await db.search_messages(1, "kubernetes")
    assert hits and hits[0]["session_id"] == "s1"
    await db.replace_messages("s1", [{"role": "user", "content": "summary only"}])
    assert len(await db.get_messages("s1")) == 1
    assert (await db.get_session("s1"))["compressions"] == 1
    assert await db.search_messages(1, "kubernetes") == []
    await db.delete_session("s1")
    assert await db.get_session("s1") is None


async def test_memory_and_pending(db):
    await db.memory_add(1, "memory", "fact")
    rows = await db.memory_list(1, "memory")
    assert rows[0]["content"] == "fact"
    await db.memory_update(rows[0]["id"], "fact2")
    assert (await db.memory_list(1, "memory"))[0]["content"] == "fact2"
    await db.memory_delete(rows[0]["id"])
    assert await db.memory_list(1, "memory") == []
    await db.set_pending(1, "s1", {"phase": "llm"})
    await db.set_pending(1, "s1", {"phase": "tools"})
    assert (await db.get_pending(1))["phase"] == "tools"
    assert len(await db.all_pending()) == 1
    await db.clear_pending(1)
    assert await db.get_pending(1) is None
