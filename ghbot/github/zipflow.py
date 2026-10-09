"""ZIP analysis for the "upload ZIP to repo" flow.

Steps the user asked for:
  1. Receive a ZIP.
  2. Ask whether existing repo files should be deleted.
  3. If the ZIP contains exactly one top-level folder, ask whether to upload the
     folder itself or its contents.
  4. Detect ``${{ secrets.NAME }}`` references in workflow files so the bot can
     offer to create each missing secret right away.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from dataclasses import dataclass, field

MAX_FILES = 3000
MAX_TOTAL_BYTES = 95 * 1024 * 1024   # GitHub blob/tree practical limit for one commit via API
MAX_FILE_BYTES = 50 * 1024 * 1024    # hard GitHub limit per file is 100MB; keep margin

_SECRET_RE = re.compile(r"\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_VAR_RE = re.compile(r"\$\{\{\s*vars\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_IGNORED_DIRS = {"__MACOSX", ".git", "node_modules", "__pycache__", ".DS_Store"}
_BUILTIN_SECRETS = {"GITHUB_TOKEN"}


@dataclass
class ZipInfo:
    files: dict[str, bytes]
    single_root: str | None
    total_bytes: int
    skipped: list[str] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    workflows: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.files)


class ZipError(Exception):
    pass


def _safe_path(name: str) -> str | None:
    name = name.replace("\\", "/")
    if name.endswith("/"):
        return None
    if ".." in name.split("/") or "\x00" in name:
        return None  # path traversal attempt — never trust normpath to "fix" it
    norm = posixpath.normpath(name)
    if norm.startswith("../") or norm.startswith("/") or norm == "." or "\x00" in norm:
        return None
    parts = norm.split("/")
    if any(p in _IGNORED_DIRS for p in parts) or parts[-1] == ".DS_Store":
        return None
    return norm


def analyze_zip(data: bytes) -> ZipInfo:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ZipError("not a valid ZIP file") from e

    files: dict[str, bytes] = {}
    skipped: list[str] = []
    total = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        path = _safe_path(info.filename)
        if path is None:
            skipped.append(info.filename)
            continue
        if info.file_size > MAX_FILE_BYTES:
            skipped.append(f"{info.filename} (too large)")
            continue
        if len(files) >= MAX_FILES:
            skipped.append(info.filename)
            continue
        content = zf.read(info)
        total += len(content)
        if total > MAX_TOTAL_BYTES:
            raise ZipError("ZIP contents exceed the 95MB upload limit")
        files[path] = content

    if not files:
        raise ZipError("ZIP is empty")

    roots = {p.split("/")[0] for p in files}
    single_root = None
    if len(roots) == 1:
        root = next(iter(roots))
        if all("/" in p for p in files):  # everything is inside that one folder
            single_root = root

    zi = ZipInfo(files=files, single_root=single_root, total_bytes=total, skipped=skipped)
    _detect_workflows(zi)
    return zi


def strip_root(zi: ZipInfo) -> ZipInfo:
    """Return a new ZipInfo with the single root folder removed from all paths."""
    if not zi.single_root:
        return zi
    prefix = zi.single_root + "/"
    files = {p[len(prefix):]: d for p, d in zi.files.items() if p.startswith(prefix)}
    out = ZipInfo(files=files, single_root=None, total_bytes=zi.total_bytes, skipped=zi.skipped)
    _detect_workflows(out)
    return out


def _detect_workflows(zi: ZipInfo) -> None:
    secrets: set[str] = set()
    variables: set[str] = set()
    workflows: list[str] = []
    for path, data in zi.files.items():
        if "/.github/workflows/" in f"/{path}" and path.endswith((".yml", ".yaml")):
            workflows.append(path)
            text = data.decode("utf-8", errors="ignore")
            secrets.update(m for m in _SECRET_RE.findall(text) if m not in _BUILTIN_SECRETS)
            variables.update(_VAR_RE.findall(text))
    zi.secrets = sorted(secrets)
    zi.variables = sorted(variables)
    zi.workflows = sorted(workflows)


def detect_secrets_in_texts(texts: dict[str, str]) -> list[str]:
    """Secrets referenced by already-pushed workflow files (used when scanning a repo)."""
    found: set[str] = set()
    for _, text in texts.items():
        found.update(m for m in _SECRET_RE.findall(text) if m not in _BUILTIN_SECRETS)
    return sorted(found)
