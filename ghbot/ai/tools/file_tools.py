"""read_file / write_file / patch / search_files — Hermes file tool semantics."""

from __future__ import annotations

import asyncio
import fnmatch
import json
import re
from pathlib import Path

from .context import ToolContext

READ_SCHEMA = {
    "name": "read_file",
    "description": "Read a text file (optionally a line range). Use this instead of cat/head/tail. Returns numbered lines.",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "offset": {"type": "integer", "description": "1-based first line (default 1)"},
            "limit": {"type": "integer", "description": "Max lines (default 400)"},
        },
        "required": ["path"],
    },
}

WRITE_SCHEMA = {
    "name": "write_file",
    "description": (
        "Write content to a file, completely replacing existing content. Creates parent directories. OVERWRITES the "
        "entire file — use 'patch' for targeted edits. For an EXISTING file call read_file first."
    ),
    "parameters": {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    },
}

PATCH_SCHEMA = {
    "name": "patch",
    "description": (
        "Targeted edit: replace old_string with new_string in a file. old_string must match exactly once unless "
        "replace_all=true. Use instead of sed/awk. Read the file first."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "replace_all": {"type": "boolean", "default": False},
        },
        "required": ["path", "old_string", "new_string"],
    },
}

SEARCH_SCHEMA = {
    "name": "search_files",
    "description": (
        "Search file contents (regex) or find files by glob. Use instead of grep/find/ls. target='content' searches "
        "inside files and returns path:line:text; target='files' lists files matching a glob pattern (e.g. '*.py')."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "description": "Directory to search (default workspace)"},
            "target": {"type": "string", "enum": ["content", "files"], "default": "content"},
            "max_results": {"type": "integer", "default": 100},
        },
        "required": ["pattern"],
    },
}

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".pytest_cache", "data"}


async def read_file(ctx: ToolContext, args: dict) -> str:
    p = ctx.resolve(args["path"])
    if not p.exists():
        return json.dumps({"error": f"not found: {p}"})
    if p.is_dir():
        entries = sorted(x.name + ("/" if x.is_dir() else "") for x in p.iterdir())
        return json.dumps({"directory": str(p), "entries": entries[:500]})
    if p.stat().st_size > 5_000_000:
        return json.dumps({"error": "file too large (>5MB); use terminal with a specific tool"})
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return json.dumps({"error": "binary file", "size": p.stat().st_size})
    lines = text.splitlines()
    offset = max(1, int(args.get("offset") or 1))
    limit = max(1, int(args.get("limit") or 400))
    chunk = lines[offset - 1: offset - 1 + limit]
    body = "\n".join(f"{offset + i:>5}| {l}" for i, l in enumerate(chunk))
    more = len(lines) - (offset - 1 + len(chunk))
    return json.dumps({"path": str(p), "total_lines": len(lines), "showing": f"{offset}-{offset + len(chunk) - 1}",
                       "remaining": max(0, more), "content": body}, ensure_ascii=False)


async def write_file(ctx: ToolContext, args: dict) -> str:
    p = ctx.resolve(args["path"])
    p.parent.mkdir(parents=True, exist_ok=True)
    content = args.get("content", "")
    p.write_text(content, encoding="utf-8")
    result = {"success": True, "path": str(p), "bytes": len(content.encode())}
    if p.suffix == ".py":
        proc = await asyncio.create_subprocess_exec("python3", "-m", "py_compile", str(p),
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, err = await proc.communicate()
        if proc.returncode != 0:
            result["syntax_error"] = err.decode(errors="replace")[-800:]
    elif p.suffix == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            result["syntax_error"] = str(e)
    return json.dumps(result, ensure_ascii=False)


async def patch(ctx: ToolContext, args: dict) -> str:
    p = ctx.resolve(args["path"])
    if not p.exists():
        return json.dumps({"error": f"not found: {p}"})
    text = p.read_text(encoding="utf-8")
    old, new = args.get("old_string", ""), args.get("new_string", "")
    if not old:
        return json.dumps({"error": "old_string is required"})
    count = text.count(old)
    if count == 0:
        return json.dumps({"error": "old_string not found in file"})
    if count > 1 and not args.get("replace_all"):
        return json.dumps({"error": f"old_string matches {count} times; add more context or set replace_all=true"})
    text = text.replace(old, new) if args.get("replace_all") else text.replace(old, new, 1)
    p.write_text(text, encoding="utf-8")
    result = {"success": True, "path": str(p), "replacements": count if args.get("replace_all") else 1}
    if p.suffix == ".py":
        proc = await asyncio.create_subprocess_exec("python3", "-m", "py_compile", str(p),
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, err = await proc.communicate()
        if proc.returncode != 0:
            result["syntax_error"] = err.decode(errors="replace")[-800:]
    return json.dumps(result, ensure_ascii=False)


def _walk(root: Path):
    for p in root.rglob("*"):
        if any(part in _SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        yield p


async def search_files(ctx: ToolContext, args: dict) -> str:
    root = ctx.resolve(args.get("path") or ".")
    if not root.exists():
        return json.dumps({"error": f"not found: {root}"})
    pattern = args.get("pattern", "")
    target = args.get("target", "content")
    max_results = int(args.get("max_results") or 100)
    results: list[str] = []

    def run():
        if target == "files":
            for p in _walk(root):
                if p.is_file() and fnmatch.fnmatch(p.name, pattern):
                    results.append(str(p.relative_to(root)))
                    if len(results) >= max_results:
                        break
        else:
            rx = re.compile(pattern)
            for p in _walk(root):
                if not p.is_file() or p.stat().st_size > 2_000_000:
                    continue
                try:
                    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                        if rx.search(line):
                            results.append(f"{p.relative_to(root)}:{i}:{line.strip()[:200]}")
                            if len(results) >= max_results:
                                return
                except (UnicodeDecodeError, OSError):
                    continue

    try:
        await asyncio.get_event_loop().run_in_executor(None, run)
    except re.error as e:
        return json.dumps({"error": f"bad regex: {e}"})
    return json.dumps({"root": str(root), "count": len(results), "results": results}, ensure_ascii=False)
