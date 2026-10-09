"""web_search / web_extract via Tavily (TAVILY_API_KEY secret)."""

from __future__ import annotations

import json

import httpx

from .context import ToolContext

SEARCH_SCHEMA = {
    "name": "web_search",
    "description": (
        "Search the web for information. Returns up to 5 results by default with titles, URLs, and content snippets. "
        "Use for documentation lookups, error messages, GitHub API details, current events."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
            "depth": {"type": "string", "enum": ["basic", "advanced"], "default": "basic"},
        },
        "required": ["query"],
    },
}

EXTRACT_SCHEMA = {
    "name": "web_extract",
    "description": "Extract clean readable content from one or more URLs (docs pages, READMEs, PDFs).",
    "parameters": {
        "type": "object",
        "properties": {"urls": {"type": "array", "items": {"type": "string"}, "maxItems": 5}},
        "required": ["urls"],
    },
}

TAVILY = "https://api.tavily.com"


async def web_search(ctx: ToolContext, args: dict) -> str:
    if not ctx.tavily_key:
        return json.dumps({"error": "web search unavailable: TAVILY_API_KEY not set"})
    body = {"api_key": ctx.tavily_key, "query": args.get("query", ""), "max_results": int(args.get("limit") or 5),
            "search_depth": args.get("depth", "basic"), "include_answer": True}
    async with httpx.AsyncClient(timeout=40) as client:
        for attempt in range(3):
            resp = await client.post(f"{TAVILY}/search", json=body)
            if resp.status_code == 429 and attempt < 2:
                import asyncio
                await asyncio.sleep(3 * (attempt + 1))
                continue
            break
    if resp.status_code != 200:
        return json.dumps({"error": f"tavily {resp.status_code}: {resp.text[:200]}"})
    data = resp.json()
    results = [{"title": r.get("title"), "url": r.get("url"), "content": (r.get("content") or "")[:800]} for r in data.get("results", [])]
    return json.dumps({"answer": data.get("answer"), "results": results}, ensure_ascii=False)


async def web_extract(ctx: ToolContext, args: dict) -> str:
    if not ctx.tavily_key:
        return json.dumps({"error": "web extract unavailable: TAVILY_API_KEY not set"})
    urls = [u for u in (args.get("urls") or []) if isinstance(u, str)][:5]
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(f"{TAVILY}/extract", json={"api_key": ctx.tavily_key, "urls": urls})
    if resp.status_code != 200:
        return json.dumps({"error": f"tavily {resp.status_code}: {resp.text[:200]}"})
    data = resp.json()
    out = [{"url": r.get("url"), "content": (r.get("raw_content") or "")[:15000]} for r in data.get("results", [])]
    return json.dumps({"results": out, "failed": data.get("failed_results", [])}, ensure_ascii=False)
