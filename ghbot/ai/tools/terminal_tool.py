"""Terminal tool (Hermes ``terminal`` semantics, local backend).

Persistent cwd + exported env per session, foreground with timeout, output
truncated with the full text saved to a file in the workspace.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import time

from .context import ToolContext

DESCRIPTION = (
    "Execute shell commands in the agent workspace. Filesystem, current working directory, and exported "
    "environment variables persist between calls (cd/export are tracked). Do NOT use cat/head/tail (use read_file), "
    "grep/find/ls (use search_files), sed/awk (use patch), echo/heredoc file creation (use write_file). Reserve "
    "terminal for: builds, installs, git, tests, scripts, network, package managers. Output is auto-truncated with "
    "the full text saved to a file — never pipe through tail/head to shorten it. Returns INSTANTLY when the command "
    "finishes, even with a high timeout."
)

SCHEMA = {
    "name": "terminal",
    "description": DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The shell command to execute"},
            "timeout": {"type": "integer", "description": "Max seconds to wait (default 180, max 900)", "minimum": 1},
            "workdir": {"type": "string", "description": "Working directory for this command (absolute or workspace-relative)"},
        },
        "required": ["command"],
    },
}

_BLOCKED = [
    re.compile(r"\brm\s+-rf\s+/(\s|$)"),
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:"),
    re.compile(r"\bmkfs\b"),
    re.compile(r">\s*/dev/sd"),
]
_SECRET_ENV = {"BOT_TOKEN", "STATE_KEY", "GH_PAT", "TAVILY_API_KEY", "TAVILY", "TELEGRAM_BOT_TOKEN"}

_EXPORT_RE = re.compile(r"^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
_CD_RE = re.compile(r"^\s*cd\s*(.*)$")


def _session(ctx: ToolContext) -> dict:
    s = ctx.extra.setdefault("terminal", {})
    s.setdefault("cwd", str(ctx.workspace))
    s.setdefault("env", {})
    return s


def _clean_env(extra: dict) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _SECRET_ENV}
    env.update(extra)
    env.setdefault("PYTHONUNBUFFERED", "1")
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


async def handle(ctx: ToolContext, args: dict) -> str:
    command = (args.get("command") or "").strip()
    if not command:
        return json.dumps({"error": "command is required"})
    for p in _BLOCKED:
        if p.search(command):
            return json.dumps({"error": "command blocked by safety policy"})
    timeout = min(int(args.get("timeout") or 180), 900)
    sess = _session(ctx)
    cwd = sess["cwd"]
    if args.get("workdir"):
        cwd = str(ctx.resolve(args["workdir"]))

    # track pure "cd" / "export" so state persists like a real shell
    m = _CD_RE.match(command)
    if m and ";" not in command and "&&" not in command and "|" not in command:
        target = m.group(1).strip() or str(ctx.workspace)
        newp = ctx.resolve(target) if not os.path.isabs(target) else ctx.resolve(target)
        if newp.is_dir():
            sess["cwd"] = str(newp)
            return json.dumps({"ok": True, "cwd": sess["cwd"]})
        return json.dumps({"error": f"no such directory: {target}", "cwd": cwd})
    m = _EXPORT_RE.match(command)
    if m and ";" not in command and "&&" not in command:
        k, v = m.group(1), m.group(2).strip().strip('"').strip("'")
        if k in _SECRET_ENV:
            return json.dumps({"error": "refusing to set a protected secret variable"})
        sess["env"][k] = v
        return json.dumps({"ok": True, "exported": k})

    ctx.workspace.mkdir(parents=True, exist_ok=True)
    # wrap so a trailing `pwd` tells us the final cwd (supports `cd x && cmd`)
    marker = f"__GHBOT_CWD_{int(time.time()*1000)}__"
    wrapped = f"{command}\n__rc=$?\necho \"{marker}$(pwd)\"\nexit $__rc"
    start = time.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-lc", wrapped, cwd=cwd, env=_clean_env(sess["env"]),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, stdin=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return json.dumps({"error": "bash not available"})
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return json.dumps({"error": f"timed out after {timeout}s", "cwd": cwd})
    text = out.decode("utf-8", errors="replace")
    new_cwd = cwd
    idx = text.rfind(marker)
    if idx >= 0:
        new_cwd = text[idx + len(marker):].strip().splitlines()[0] if text[idx + len(marker):].strip() else cwd
        text = text[:idx].rstrip("\n")
    if os.path.isdir(new_cwd):
        sess["cwd"] = new_cwd
    result = {"exit_code": proc.returncode, "cwd": sess["cwd"], "duration_s": round(time.time() - start, 2)}
    if len(text) > 30_000:
        logs = ctx.workspace / ".ghbot_logs"
        logs.mkdir(exist_ok=True)
        f = logs / f"term_{int(start)}.log"
        f.write_text(text, encoding="utf-8")
        result["full_output_file"] = str(f)
        text = text[:20_000] + f"\n\n[... {len(text) - 26_000} chars omitted; full output in {f} (use read_file) ...]\n\n" + text[-6_000:]
    result["output"] = text
    return json.dumps(result, ensure_ascii=False)
