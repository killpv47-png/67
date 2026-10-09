"""receive_file — download the user's latest incoming file and expose its full contents.

Combines the old telegram_download_file with ZIP extraction so the agent can, in one call,
grab whatever the user just sent and see everything inside it. Non-ZIP files are saved and
their path returned (read_file works on them). ZIPs are extracted into
``workspace/incoming/`` and a manifest of every file is returned; the agent can then
``read_file`` any extracted file, or pass ``read=<path>`` to get a specific file's contents
right here.

The incoming file is resolved from ``ctx.incoming_file`` (set by the ai_chat handler) or an
explicit ``file_id``. ``ctx.incoming_file`` is a dict like ``{"file_id": ..., "name": ...}``.
"""

from __future__ import annotations

import io
import json
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from .context import ToolContext

DESCRIPTION = (
    "Download the file the user just sent (ZIP or any document/photo) and make its full "
    "contents available. If it's a ZIP, extract it into the workspace and return a manifest "
    "of every file inside (use read=<path> to get one file's contents, or read_file afterwards). "
    "If it's any other file, save it and return its path. file_id is optional — defaults to the "
    "latest incoming file. Use this whenever the user sends you a file to inspect."
)

SCHEMA = {
    "name": "receive_file",
    "description": DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Optional Telegram file_id (defaults to the latest incoming file)"},
            "read": {"type": "string", "description": "Optional path of a file inside the ZIP to return its contents (text files only)"},
            "max_text": {"type": "integer", "description": "Per-file text preview limit in the manifest (default 2000 chars)"},
        },
    },
}

_MAX = 50 * 1024 * 1024  # Telegram download limit
_TEXT_EXTS = {".py", ".js", ".ts", ".json", ".yaml", ".yml", ".md", ".txt", ".toml", ".ini", ".cfg",
              ".sh", ".bash", ".html", ".css", ".xml", ".sql", ".rs", ".go", ".java", ".c", ".h",
              ".cpp", ".hpp", ".rb", ".php", ".lua", ".r", ".swift", ".kt", ".dockerfile", ".gitignore",
              ".env.example", ".properties", ".conf", ".gitattributes", ".gitmodules", ".editorconfig"}


def _is_text(name: str) -> bool:
    return Path(name).suffix.lower() in _TEXT_EXTS or Path(name).name.lower() in {
        "dockerfile", "makefile", "readme", "license", "changelog", "procfile", "vagrantfile", "justfile"}


def _download(ctx: ToolContext, file_id: str) -> tuple[bytes, str]:
    """Fetch a Telegram file by id. Returns (content, original_name)."""
    if not ctx.bot_token:
        raise RuntimeError("no bot token available to download files")
    token = ctx.bot_token
    get_url = f"https://api.telegram.org/bot{token}/getFile?file_id={urllib.parse.quote(file_id)}"
    with urllib.request.urlopen(get_url, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    if not data.get("ok"):
        raise RuntimeError(f"telegram error: {data.get('description', 'unknown')}")
    res = data.get("result", {})
    file_path = res.get("file_path")
    if not file_path:
        raise RuntimeError("no file_path in response")
    size = res.get("file_size", 0)
    if size > _MAX:
        raise RuntimeError(f"file too large ({size} bytes > 50MB)")
    dl_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    with urllib.request.urlopen(dl_url, timeout=300) as resp:
        content = resp.read()
    name = file_path.rsplit("/", 1)[-1] or "incoming.bin"
    return content, name


async def handle(ctx: ToolContext, args: dict) -> str:
    file_id = (args.get("file_id") or "").strip()
    if not file_id:
        incoming = ctx.incoming_file or {}
        file_id = (incoming.get("file_id") or "").strip()
        fallback_name = incoming.get("name") or "incoming.bin"
    else:
        fallback_name = "incoming.bin"
    if not file_id:
        return json.dumps({"error": "no file_id and no incoming file recorded — send a file first"})

    try:
        content, name = _download(ctx, file_id)
    except Exception as e:
        return json.dumps({"error": f"download failed: {e}"})

    # save the raw file
    ctx.workspace.mkdir(parents=True, exist_ok=True)
    raw = ctx.workspace / name
    raw.write_bytes(content)

    # not a zip -> just report the saved file
    if not zipfile.is_zipfile(io.BytesIO(content)):
        return json.dumps({
            "success": True,
            "type": "file",
            "path": str(raw),
            "size": len(content),
            "name": name,
            "hint": "use read_file on this path to see its contents",
        }, ensure_ascii=False)

    # zip -> extract into workspace/incoming/
    dest = ctx.workspace / "incoming"
    dest.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    read_req = (args.get("read") or "").strip()
    read_result = None
    max_text = int(args.get("max_text") or 2000)
    total = 0
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as e:
        return json.dumps({"error": f"not a valid ZIP: {e}"})

    for info in zf.infolist():
        if info.is_dir():
            continue
        # safe path: reject traversal
        rel = info.filename.replace("\\", "/")
        if ".." in rel.split("/") or rel.startswith("/"):
            continue
        target = (dest / rel).resolve()
        if not str(target).startswith(str(dest.resolve())):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        data = zf.read(info)
        target.write_bytes(data)
        total += len(data)
        entry = {"path": rel, "size": len(data)}
        if _is_text(rel) and len(data) <= max_text:
            try:
                entry["preview"] = data.decode("utf-8")
            except UnicodeDecodeError:
                pass
        manifest.append(entry)
        if read_req and rel == read_req:
            try:
                read_result = data.decode("utf-8")
            except UnicodeDecodeError:
                read_result = None

    if read_req and read_result is None:
        # maybe the requested file exists but is binary / not found
        found = [m["path"] for m in manifest if m["path"] == read_req]
        if found:
            read_result = "(binary file — use read_file on the extracted path)"
        else:
            return json.dumps({"error": f"file not in ZIP: {read_req}", "manifest": [m["path"] for m in manifest]})

    out = {
        "success": True,
        "type": "zip",
        "zip_path": str(raw),
        "extracted_to": str(dest),
        "file_count": len(manifest),
        "total_bytes": total,
        "manifest": manifest,
    }
    if read_result is not None:
        out["read"] = read_result
    return json.dumps(out, ensure_ascii=False)
