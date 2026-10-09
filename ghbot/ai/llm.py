"""OpenAI-compatible chat client with Hermes-style error classification.

The user's hard requirement: when the model is rate-limited the task must NOT
die — wait, then resume the *same* request.  ``chat()`` therefore loops
internally on ``rate_limit`` / ``server_error`` / network errors with capped
exponential backoff (honouring ``Retry-After``), reporting each wait through
``on_wait`` so the Telegram UI can show "waiting Ns".  Non-retryable errors
(auth, context-too-long, bad request) raise ``LLMError`` with a ``kind`` the
agent loop uses to decide between compaction and surfacing the error.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx

log = logging.getLogger(__name__)

WaitCB = Callable[[float, str, int], Awaitable[None]]

_CONTEXT_PATTERNS = re.compile(
    r"context[_ ]length|maximum context|too many tokens|prompt is too long|exceeds the limit|input is too long|"
    r"max_tokens|token limit|reduce the length", re.I)
_RATE_PATTERNS = re.compile(r"rate.?limit|too many requests|quota|overloaded|capacity|throttl|try again later|resource.?exhausted", re.I)
_AUTH_PATTERNS = re.compile(r"invalid.*api.?key|unauthorized|authentication|incorrect api key|no auth", re.I)


class LLMError(Exception):
    def __init__(self, kind: str, message: str, status: int | None = None):
        super().__init__(message)
        self.kind = kind  # auth | context_length | bad_request | model_not_found | exhausted | unknown
        self.status = status


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[dict] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)

    def as_message(self) -> dict:
        msg: dict[str, Any] = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = self.tool_calls
        return msg


def classify(status: int | None, body: str) -> str:
    text = body or ""
    if status == 429:
        return "rate_limit"
    if status in (401, 403) or _AUTH_PATTERNS.search(text):
        return "auth"
    if status == 404 and "model" in text.lower():
        return "model_not_found"
    if _CONTEXT_PATTERNS.search(text):
        return "context_length"
    if _RATE_PATTERNS.search(text):
        return "rate_limit"
    if status is not None and status >= 500:
        return "server_error"
    if status == 400:
        return "bad_request"
    return "unknown"


def _retry_after(headers: httpx.Headers, attempt: int) -> float:
    ra = headers.get("retry-after")
    if ra:
        try:
            return min(float(ra), 600.0)
        except ValueError:
            pass
    for h in ("x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        v = headers.get(h)
        if v:
            m = re.match(r"(?:(\d+)m)?(?:([\d.]+)s)?(?:(\d+)ms)?", v)
            if m and any(m.groups()):
                secs = float(m.group(1) or 0) * 60 + float(m.group(2) or 0) + float(m.group(3) or 0) / 1000
                if secs > 0:
                    return min(secs + 1, 600.0)
    return min(5.0 * (2 ** attempt), 300.0)


class LLMClient:
    def __init__(self, base_url: str, api_key: str, *, timeout: float = 180.0, on_wait: WaitCB | None = None,
                 max_retry_minutes: float = 45.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.on_wait = on_wait
        self.max_retry_seconds = max_retry_minutes * 60
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=20.0),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                     "HTTP-Referer": "https://github.com", "X-Title": "GITHUB_AI"},
        )

    async def aclose(self):
        await self._client.aclose()

    async def list_models(self) -> list[str]:
        resp = await self._client.get(f"{self.base_url}/models")
        if resp.status_code != 200:
            raise LLMError(classify(resp.status_code, resp.text), resp.text[:300], resp.status_code)
        data = resp.json()
        items = data.get("data", data if isinstance(data, list) else [])
        ids = []
        for m in items:
            mid = m.get("id") if isinstance(m, dict) else m
            if isinstance(mid, str):
                ids.append(mid)
        return sorted(set(ids))

    async def chat(self, *, model: str, messages: list[dict], tools: list[dict] | None = None,
                   temperature: float = 0.2, max_tokens: int | None = None, cancel: asyncio.Event | None = None) -> LLMResponse:
        body: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if max_tokens:
            body["max_tokens"] = max_tokens

        waited = 0.0
        attempt = 0
        while True:
            if cancel and cancel.is_set():
                raise asyncio.CancelledError()
            try:
                resp = await self._client.post(f"{self.base_url}/chat/completions", json=body)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                kind, status, text, headers = "server_error", None, str(e), httpx.Headers()
            else:
                if resp.status_code == 200:
                    return self._parse(resp.json())
                status, text, headers = resp.status_code, resp.text, resp.headers
                kind = classify(status, text)

            if kind in ("rate_limit", "server_error"):
                wait = _retry_after(headers, attempt)
                if waited + wait > self.max_retry_seconds:
                    raise LLMError("exhausted", f"gave up after {int(waited)}s of retries: {text[:200]}", status)
                attempt += 1
                waited += wait
                log.warning("LLM %s (status=%s) — waiting %.0fs (attempt %d)", kind, status, wait, attempt)
                if self.on_wait:
                    try:
                        await self.on_wait(wait, kind, attempt)
                    except Exception:  # pragma: no cover
                        pass
                # sleep in small slices so cancel is responsive
                end = asyncio.get_event_loop().time() + wait
                while asyncio.get_event_loop().time() < end:
                    if cancel and cancel.is_set():
                        raise asyncio.CancelledError()
                    await asyncio.sleep(min(1.0, end - asyncio.get_event_loop().time()))
                continue
            raise LLMError(kind, text[:500], status)

    @staticmethod
    def _parse(data: dict) -> LLMResponse:
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("unknown", f"empty choices: {json.dumps(data)[:300]}")
        ch = choices[0]
        msg = ch.get("message") or {}
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments")
            if not isinstance(args, str):
                args = json.dumps(args or {})
            tool_calls.append({"id": tc.get("id") or f"call_{len(tool_calls)}", "type": "function",
                               "function": {"name": fn.get("name", ""), "arguments": args}})
        content = msg.get("content")
        if isinstance(content, list):  # some providers return content parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return LLMResponse(content=content, tool_calls=tool_calls, finish_reason=ch.get("finish_reason"),
                           usage=data.get("usage") or {}, raw=data)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            total += estimate_tokens(c)
        if m.get("tool_calls"):
            total += estimate_tokens(json.dumps(m["tool_calls"]))
        total += 4
    return total
