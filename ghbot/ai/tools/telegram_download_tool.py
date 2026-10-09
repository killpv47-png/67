"""telegram_download_file — download a file the user sent to the bot into the workspace.

The user sends a document/photo to the chat; the ai_chat handler records its file_id
in the DB (kv:incoming:<tg_id>). This tool fetches the file via the Telegram Bot API
(getFile + file download) and saves it into the workspace so the agent can read it.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.parse

from .context import ToolContext

DESCRIPTION = (
    "Download a file the user sent to the bot (document/photo) into the workspace. "
    "file_id is the Telegram file identifier (the bot records the latest incoming file "
    "as 'incoming_file' in context). filename is optional; defaults to the original name. "
    "Use when the user sends you a file and you need to read its contents."
)

SCHEMA = {
    "name": "telegram_download_file",
    "description": DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Telegram file_id of the incoming file"},
            "filename": {"type": "string", "description": "Optional name to save as (default: original)"},
        },
        "required": ["file_id"],
    },
}

_MAX = 50 * 1024 * 1024  # Telegram download limit


async def handle(ctx: ToolContext, args: dict) -> str:
    file_id = (args.get("file_id") or "").strip()
    if not file_id:
        return json.dumps({"error": "file_id is required"})
    if not ctx.bot_token:
        return json.dumps({"error": "no bot token available to download files"})

    token = ctx.bot_token
    # 1. resolve file path
    get_url = f"https://api.telegram.org/bot{token}/getFile?file_id={urllib.parse.quote(file_id)}"
    try:
        with urllib.request.urlopen(get_url, timeout=60) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return json.dumps({"error": f"getFile failed: {e}"})
    if not data.get("ok"):
        return json.dumps({"error": f"telegram error: {data.get('description', 'unknown')}"})
    res = data.get("result", {})
    file_path = res.get("file_path")
    if not file_path:
        return json.dumps({"error": "no file_path in response"})
    size = res.get("file_size", 0)
    if size > _MAX:
        return json.dumps({"error": f"file too large ({size} bytes > 50MB)"})

    # 2. download
    dl_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    try:
        with urllib.request.urlopen(dl_url, timeout=300) as resp:
            content = resp.read()
    except Exception as e:
        return json.dumps({"error": f"download failed: {e}"})

    # 3. save to workspace
    name = (args.get("filename") or "").strip() or file_path.rsplit("/", 1)[-1] or "incoming.bin"
    ctx.workspace.mkdir(parents=True, exist_ok=True)
    dest = ctx.workspace / name
    dest.write_bytes(content)
    return json.dumps({"success": True, "path": str(dest), "size": len(content), "file_id": file_id})
