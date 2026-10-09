"""Scripted OpenAI-compatible fake used by AI tests (httpx MockTransport)."""

import json

import httpx

from ghbot.ai.llm import LLMClient


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.requests: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "m1"}, {"id": "m2"}]})
        self.requests.append(json.loads(request.content))
        item = self.script.pop(0)
        if isinstance(item, tuple):
            status, body, headers = item
            return httpx.Response(status, json=body, headers=headers)
        return httpx.Response(200, json=item)


def text_resp(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}]}


def tool_resp(name, args, call_id="c1"):
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]},
        "finish_reason": "tool_calls"}]}


def make_client(fake: FakeLLM, **kw) -> LLMClient:
    c = LLMClient("https://fake/v1", "sk-test", **kw)
    c._client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler), headers=c._client.headers)
    return c
