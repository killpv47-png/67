"""State checkpoint: encrypted SQLite snapshot stored in the HOST repo.

Where: ``state/state.enc`` on branch ``ghbot-state`` of the repo that runs the
workflow.  The payload is the full ``ghbot.db`` (after a WAL checkpoint) + the AI
home dir (skills written by GITHUB_AI) packed as JSON, encrypted with STATE_KEY
(AES-256-GCM).  Tokens inside the DB are already encrypted individually, and the
whole file is encrypted again — nothing in plain text ever leaves the runner.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from pathlib import Path

from ..core.crypto import DecryptError, decrypt, encrypt
from ..core.db import Database
from ..github.client import GitHubClient, GitHubError

log = logging.getLogger(__name__)

STATE_BRANCH = "ghbot-state"
STATE_PATH = "state/state.enc"


def pack_state(db_bytes: bytes, home_dir: Path, state_key: str) -> bytes:
    files: dict[str, str] = {}
    skills_dir = home_dir / "skills"
    if skills_dir.exists():
        for p in skills_dir.rglob("*"):
            if p.is_file() and p.stat().st_size < 400_000:
                files[str(p.relative_to(home_dir))] = p.read_text(encoding="utf-8", errors="replace")
    payload = {"v": 1, "ts": time.time(), "db": base64.b64encode(db_bytes).decode(), "home": files}
    return encrypt(json.dumps(payload).encode(), state_key)


def unpack_state(blob: bytes, state_key: str) -> dict:
    return json.loads(decrypt(blob, state_key))


class Checkpointer:
    def __init__(self, db: Database, *, host_repo: str, gh_pat: str, state_key: str, home_dir: Path):
        self.db = db
        self.host_repo = host_repo
        self.gh_pat = gh_pat
        self.state_key = state_key
        self.home_dir = home_dir
        self._last_hash: str | None = None
        self.last_saved_at: float | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.host_repo and self.gh_pat and self.state_key)

    async def save(self, *, force: bool = False) -> bool:
        if not self.enabled:
            return False
        await self.db.checkpoint()
        db_bytes = self.db.path.read_bytes()
        plain_hash = hashlib.sha256(db_bytes).hexdigest()
        if not force and plain_hash == self._last_hash:
            return False
        blob = pack_state(db_bytes, self.home_dir, self.state_key)
        async with GitHubClient(self.gh_pat) as gh:
            try:
                await self._ensure_branch(gh)
                await gh.upsert_file(self.host_repo, STATE_PATH, blob,
                                     f"ghbot checkpoint {time.strftime('%Y-%m-%d %H:%M:%S')}", STATE_BRANCH)
            except GitHubError as e:
                log.error("checkpoint save failed: %s", e)
                raise
        self._last_hash = plain_hash
        self.last_saved_at = time.time()
        log.info("checkpoint saved (%d bytes)", len(blob))
        return True

    async def _ensure_branch(self, gh: GitHubClient) -> None:
        try:
            await gh.get(f"/repos/{self.host_repo}/git/ref/heads/{STATE_BRANCH}")
            return
        except GitHubError as e:
            if e.status != 404:
                raise
        repo = await gh.get_repo(self.host_repo)
        ref = await gh.get(f"/repos/{self.host_repo}/git/ref/heads/{repo['default_branch']}")
        await gh.post(f"/repos/{self.host_repo}/git/refs", {"ref": f"refs/heads/{STATE_BRANCH}", "sha": ref["object"]["sha"]})

    async def restore_if_needed(self) -> str:
        """Called BEFORE the DB is opened. Returns 'restored' | 'fresh' | 'skipped' | 'failed'."""
        if not self.enabled:
            return "skipped"
        if self.db.path.exists() and self.db.path.stat().st_size > 0:
            return "skipped"
        async with GitHubClient(self.gh_pat) as gh:
            try:
                data = await gh.get_contents(self.host_repo, STATE_PATH, STATE_BRANCH)
            except GitHubError as e:
                if e.status == 404:
                    return "fresh"
                log.error("checkpoint fetch failed: %s", e)
                return "failed"
            if isinstance(data, dict) and data.get("encoding") == "base64" and data.get("content"):
                blob = base64.b64decode(data["content"])
            else:
                blob_data = await gh.get(f"/repos/{self.host_repo}/git/blobs/{data['sha']}")
                blob = base64.b64decode(blob_data["content"])
        try:
            payload = unpack_state(blob, self.state_key)
        except DecryptError:
            log.error("checkpoint exists but STATE_KEY does not match — starting fresh (old state kept on branch)")
            return "failed"
        self.apply_payload(payload)
        log.info("checkpoint restored from %s@%s (saved %s)", self.host_repo, STATE_BRANCH, time.ctime(payload.get("ts", 0)))
        return "restored"

    def apply_payload(self, payload: dict) -> None:
        self.db.path.parent.mkdir(parents=True, exist_ok=True)
        db_bytes = base64.b64decode(payload["db"])
        self.db.path.write_bytes(db_bytes)
        for rel, text in (payload.get("home") or {}).items():
            target = (self.home_dir / rel).resolve()
            if str(target).startswith(str(self.home_dir.resolve())):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
        self._last_hash = hashlib.sha256(db_bytes).hexdigest()
