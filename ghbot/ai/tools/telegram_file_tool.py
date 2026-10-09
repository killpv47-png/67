"""telegram_send_file — send a file (ZIP, image, log) to the user's Telegram chat.

The bot has no built-in "send file" surface, so this tool delivers files directly
via the Telegram Bot API ``sendDocument`` multipart call.  The bot token lives in
``ToolContext.bot_token`` (injected from settings, never printed).
"""

from __future__ import annotations

import json
import os
import urllib.request
import uuid
from pathlib import Path

from .context import ToolContext

DESCRIPTION = (
    "Send a file (ZIP, image, log, etc.) or a whole folder to the user's Telegram chat. "
    "If path is a directory it is zipped first (into the workspace) and sent as a ZIP. "
    "Use when the user wants a file delivered (e.g. a ZIP of repos, a log, a screenshot). "
    "path is the file or folder to send (absolute or workspace-relative). caption is optional short text."
)

SCHEMA = {
    "name": "telegram_send_file",
    "description": DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file or folder to send (absolute or workspace-relative)"},
            "caption": {"type": "string", "description": "Optional caption text"},
        },
        "required": ["path"],
    },
}

_MAX = 50 * 1024 * 1024  # Telegram document limit


async def handle(ctx: ToolContext, args: dict) -> str:
    path = args.get("path", "")
    if not path:
        return json.dumps({"error": "path is required"})
    p = ctx.resolve(path)
    if not p.exists():
        return json.dumps({"error": f"not found: {p}"})

    # directories are zipped first
    if p.is_dir():
        import shutil
        import tempfile
        ctx.workspace.mkdir(parents=True, exist_ok=True)
        zname = p.name.rstrip("/") or "folder"
        zpath = ctx.workspace / f"{zname}.zip"
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / zname
            shutil.copytree(p, base)
            shutil.make_archive(str(zpath.with_suffix("")), "zip", root_dir=td, base_dir=zname)
        p = zpath

    if not p.is_file():
        return json.dumps({"error": f"not a file: {p}"})
    size = p.stat().st_size
    if size > _MAX:
        return json.dumps({"error": f"file too large for Telegram ({size} bytes > 50MB)"})
    if not ctx.bot_token:
        return json.dumps({"error": "no bot token available to send files"})

    token = ctx.bot_token
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
    filename = p.name
    caption = (args.get("caption") or "").strip()

    body = bytearray()
    body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{ctx.tg_id}\r\n".encode()
    if caption:
        body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n".encode()
    body += (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{filename}\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    body += p.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(url, data=bytes(body), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:  # network / Telegram errors
        return json.dumps({"error": f"send failed: {e}"})
    if not data.get("ok"):
        return json.dumps({"error": f"telegram error: {data.get('description', 'unknown')}"})
    res = data.get("result", {})
    return json.dumps({
        "success": True,
        "file_name": res.get("document", {}).get("file_name", filename),
        "file_size": res.get("document", {}).get("file_size", size),
        "message_id": res.get("message_id"),
    })
