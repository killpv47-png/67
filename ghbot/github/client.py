"""Async GitHub REST client with rate-limit awareness, retries and pagination.

Design rules
  * Every call goes through ``_request`` which handles: primary rate limit
    (X-RateLimit-Remaining==0 -> sleep until reset), secondary rate limit
    (403/429 with Retry-After), transient 5xx (exponential backoff), and
    network errors.  A call never crashes the bot — it raises a typed
    ``GitHubError`` the caller can show to the user.
  * ``on_wait`` callback lets the UI notify the user when we are sleeping on a
    rate limit instead of appearing frozen.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any, Awaitable, Callable, Optional

import httpx
from nacl import encoding, public

log = logging.getLogger(__name__)

API = "https://api.github.com"
WaitCB = Callable[[float, str], Awaitable[None]]


class GitHubError(Exception):
    def __init__(self, status: int, message: str, data: Any = None):
        super().__init__(f"GitHub {status}: {message}")
        self.status = status
        self.message = message
        self.data = data


class RateLimited(GitHubError):
    def __init__(self, reset_in: float):
        super().__init__(429, f"rate limited, retry in {int(reset_in)}s")
        self.reset_in = reset_in


def _parse_retry(headers: httpx.Headers) -> float | None:
    ra = headers.get("retry-after")
    if ra and ra.isdigit():
        return float(ra)
    if headers.get("x-ratelimit-remaining") == "0":
        reset = headers.get("x-ratelimit-reset")
        if reset and reset.isdigit():
            return max(1.0, float(reset) - time.time() + 1)
    return None


class GitHubClient:
    def __init__(self, token: str, *, on_wait: WaitCB | None = None, timeout: float = 40.0, max_wait: float = 900.0):
        self.token = token
        self.on_wait = on_wait
        self.max_wait = max_wait
        self._client = httpx.AsyncClient(
            base_url=API,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "ghbot-telegram/1.0",
            },
            follow_redirects=True,
        )
        self.scopes: list[str] | None = None
        self.rate_remaining: int | None = None
        self.rate_limit: int | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "GitHubClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    # ------------------------------------------------------------------ core
    async def _request(self, method: str, path: str, *, retries: int = 6, **kw) -> httpx.Response:
        url = path if path.startswith("http") else path
        backoff = 1.5
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = await self._client.request(method, url, **kw)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_exc = e
                await asyncio.sleep(min(backoff**attempt, 20))
                continue

            if "x-oauth-scopes" in resp.headers:
                raw = resp.headers.get("x-oauth-scopes", "")
                self.scopes = [s.strip() for s in raw.split(",") if s.strip()] if raw else []
            if resp.headers.get("x-ratelimit-remaining", "").isdigit():
                self.rate_remaining = int(resp.headers["x-ratelimit-remaining"])
            if resp.headers.get("x-ratelimit-limit", "").isdigit():
                self.rate_limit = int(resp.headers["x-ratelimit-limit"])

            if resp.status_code in (403, 429):
                wait = _parse_retry(resp.headers)
                body = (resp.text or "").lower()
                if wait is not None or "rate limit" in body or "abuse" in body:
                    wait = wait or min(60.0 * (attempt + 1), 300.0)
                    if wait > self.max_wait:
                        raise RateLimited(wait)
                    if self.on_wait:
                        try:
                            await self.on_wait(wait, "github_rate_limit")
                        except Exception:  # pragma: no cover
                            pass
                    log.warning("GitHub rate limited; sleeping %.0fs", wait)
                    await asyncio.sleep(wait)
                    continue
            if 500 <= resp.status_code < 600 and attempt < retries - 1:
                await asyncio.sleep(min(backoff**attempt, 20))
                continue
            return resp
        raise GitHubError(0, f"network error: {last_exc}") if last_exc else GitHubError(0, "retries exhausted")

    async def _json(self, method: str, path: str, *, ok=(200, 201, 202, 204), **kw) -> Any:
        resp = await self._request(method, path, **kw)
        if resp.status_code not in ok:
            try:
                data = resp.json()
                msg = data.get("message", resp.text) if isinstance(data, dict) else resp.text
                if isinstance(data, dict) and data.get("errors"):
                    msg += " — " + "; ".join(
                        e.get("message") or f"{e.get('field')}: {e.get('code')}" if isinstance(e, dict) else str(e)
                        for e in data["errors"]
                    )
            except Exception:
                data, msg = None, resp.text
            raise GitHubError(resp.status_code, msg, data)
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    async def get(self, path: str, **params) -> Any:
        return await self._json("GET", path, params=params or None)

    async def post(self, path: str, json: Any = None, **kw) -> Any:
        return await self._json("POST", path, json=json, **kw)

    async def put(self, path: str, json: Any = None, **kw) -> Any:
        return await self._json("PUT", path, json=json, **kw)

    async def patch(self, path: str, json: Any = None) -> Any:
        return await self._json("PATCH", path, json=json)

    async def delete(self, path: str, json: Any = None) -> Any:
        return await self._json("DELETE", path, json=json)

    async def paginate(self, path: str, *, key: str | None = None, per_page: int = 100, max_pages: int = 20, **params) -> list:
        out: list = []
        page = 1
        while page <= max_pages:
            data = await self.get(path, per_page=per_page, page=page, **params)
            items = data.get(key, []) if key and isinstance(data, dict) else data
            if not items:
                break
            out.extend(items)
            if len(items) < per_page:
                break
            page += 1
        return out

    # ------------------------------------------------------------- identity
    async def me(self) -> dict:
        return await self.get("/user")

    async def rate_limit_status(self) -> dict:
        return await self.get("/rate_limit")

    async def probe_fine_grained(self, login: str) -> dict:
        """For fine-grained tokens (no scopes header) infer capabilities empirically."""
        probe = {"can_read": True, "can_write": False, "can_workflow": False, "can_delete": False, "can_admin": False}
        try:
            repos = await self.get("/user/repos", per_page=1, affiliation="owner", sort="updated")
        except GitHubError:
            return probe
        if not repos:
            return probe
        full = repos[0]["full_name"]
        perms = repos[0].get("permissions", {})
        probe["can_write"] = bool(perms.get("push"))
        probe["can_admin"] = bool(perms.get("admin"))
        probe["can_delete"] = bool(perms.get("admin"))
        try:
            await self.get(f"/repos/{full}/actions/secrets/public-key")
            probe["can_workflow"] = True
        except GitHubError:
            pass
        return probe

    # ---------------------------------------------------------------- repos
    async def list_repos(self, *, affiliation: str = "owner,collaborator,organization_member", max_pages: int = 10) -> list[dict]:
        return await self.paginate("/user/repos", affiliation=affiliation, sort="updated", max_pages=max_pages)

    async def get_repo(self, full: str) -> dict:
        return await self.get(f"/repos/{full}")

    async def create_repo(self, *, name: str, private: bool, description: str = "", auto_init: bool = True,
                          gitignore_template: str | None = None, license_template: str | None = None,
                          has_issues: bool = True, has_wiki: bool = False, has_projects: bool = False,
                          org: str | None = None, is_template: bool = False, homepage: str = "") -> dict:
        body: dict[str, Any] = {
            "name": name, "private": private, "description": description or "", "auto_init": auto_init,
            "has_issues": has_issues, "has_wiki": has_wiki, "has_projects": has_projects, "is_template": is_template,
        }
        if homepage:
            body["homepage"] = homepage
        if gitignore_template:
            body["gitignore_template"] = gitignore_template
        if license_template:
            body["license_template"] = license_template
        path = f"/orgs/{org}/repos" if org else "/user/repos"
        return await self.post(path, body)

    async def update_repo(self, full: str, **fields) -> dict:
        return await self.patch(f"/repos/{full}", fields)

    async def delete_repo(self, full: str) -> None:
        await self.delete(f"/repos/{full}")

    async def list_orgs(self) -> list[dict]:
        try:
            return await self.get("/user/orgs")
        except GitHubError:
            return []

    async def list_branches(self, full: str) -> list[dict]:
        return await self.paginate(f"/repos/{full}/branches", max_pages=3)

    async def get_tree(self, full: str, ref: str) -> dict:
        return await self.get(f"/repos/{full}/git/trees/{ref}", recursive="1")

    async def get_contents(self, full: str, path: str, ref: str | None = None) -> Any:
        return await self.get(f"/repos/{full}/contents/{path}", **({"ref": ref} if ref else {}))

    async def get_file_text(self, full: str, path: str, ref: str | None = None) -> str | None:
        try:
            data = await self.get_contents(full, path, ref)
        except GitHubError as e:
            if e.status == 404:
                return None
            raise
        if isinstance(data, dict) and data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return None

    async def put_file(self, full: str, path: str, content: bytes, message: str, branch: str | None = None,
                       sha: str | None = None) -> dict:
        body: dict[str, Any] = {"message": message, "content": base64.b64encode(content).decode()}
        if branch:
            body["branch"] = branch
        if sha:
            body["sha"] = sha
        return await self.put(f"/repos/{full}/contents/{path}", body)

    async def upsert_file(self, full: str, path: str, content: bytes, message: str, branch: str | None = None) -> dict:
        sha = None
        try:
            existing = await self.get_contents(full, path, branch)
            if isinstance(existing, dict):
                sha = existing.get("sha")
        except GitHubError as e:
            if e.status != 404:
                raise
        return await self.put_file(full, path, content, message, branch, sha)

    # ------------------------------------------------------ git data (bulk)
    async def commit_tree(self, full: str, branch: str, files: dict[str, bytes], message: str, *,
                          replace_all: bool, progress: Callable[[str], Awaitable[None]] | None = None) -> dict:
        """Create ONE commit containing many files using the Git Data API.

        files: {"path/in/repo": bytes}
        replace_all=True  -> the new tree contains only ``files`` (old files deleted).
        replace_all=False -> files are layered on top of the existing tree.
        """
        async def say(msg: str):
            if progress:
                await progress(msg)

        ref = None
        try:
            ref = await self.get(f"/repos/{full}/git/ref/heads/{branch}")
        except GitHubError as e:
            if e.status != 404 and e.status != 409:
                raise
        base_commit_sha = ref["object"]["sha"] if ref else None
        base_tree_sha = None
        if base_commit_sha:
            commit = await self.get(f"/repos/{full}/git/commits/{base_commit_sha}")
            base_tree_sha = commit["tree"]["sha"]

        await say(f"Uploading {len(files)} blobs…")
        tree: list[dict] = []
        sem = asyncio.Semaphore(8)
        done = 0

        async def make_blob(path: str, data: bytes):
            nonlocal done
            async with sem:
                blob = await self.post(
                    f"/repos/{full}/git/blobs",
                    {"content": base64.b64encode(data).decode(), "encoding": "base64"},
                )
                tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
                done += 1
                if done % 25 == 0:
                    await say(f"Blobs: {done}/{len(files)}")

        await asyncio.gather(*(make_blob(p, d) for p, d in files.items()))
        tree.sort(key=lambda t: t["path"])

        await say("Building tree…")
        tree_body: dict[str, Any] = {"tree": tree}
        if base_tree_sha and not replace_all:
            tree_body["base_tree"] = base_tree_sha
        new_tree = await self.post(f"/repos/{full}/git/trees", tree_body)

        await say("Creating commit…")
        commit_body: dict[str, Any] = {"message": message, "tree": new_tree["sha"]}
        if base_commit_sha:
            commit_body["parents"] = [base_commit_sha]
        new_commit = await self.post(f"/repos/{full}/git/commits", commit_body)

        if ref:
            await self.patch(f"/repos/{full}/git/refs/heads/{branch}", {"sha": new_commit["sha"], "force": False})
        else:
            await self.post(f"/repos/{full}/git/refs", {"ref": f"refs/heads/{branch}", "sha": new_commit["sha"]})
        return new_commit

    # -------------------------------------------------------------- secrets
    async def repo_public_key(self, full: str) -> dict:
        return await self.get(f"/repos/{full}/actions/secrets/public-key")

    @staticmethod
    def seal(public_key_b64: str, value: str) -> str:
        pk = public.PublicKey(public_key_b64.encode(), encoding.Base64Encoder())
        sealed = public.SealedBox(pk).encrypt(value.encode())
        return base64.b64encode(sealed).decode()

    async def list_secrets(self, full: str) -> list[dict]:
        data = await self.get(f"/repos/{full}/actions/secrets", per_page=100)
        return data.get("secrets", [])

    async def set_secret(self, full: str, name: str, value: str) -> None:
        key = await self.repo_public_key(full)
        await self.put(
            f"/repos/{full}/actions/secrets/{name}",
            {"encrypted_value": self.seal(key["key"], value), "key_id": key["key_id"]},
        )

    async def delete_secret(self, full: str, name: str) -> None:
        await self.delete(f"/repos/{full}/actions/secrets/{name}")

    async def list_variables(self, full: str) -> list[dict]:
        try:
            data = await self.get(f"/repos/{full}/actions/variables", per_page=100)
            return data.get("variables", [])
        except GitHubError:
            return []

    async def set_variable(self, full: str, name: str, value: str) -> None:
        try:
            await self.post(f"/repos/{full}/actions/variables", {"name": name, "value": value})
        except GitHubError as e:
            if e.status == 409:
                await self.patch(f"/repos/{full}/actions/variables/{name}", {"name": name, "value": value})
            else:
                raise

    # -------------------------------------------------------------- actions
    async def list_workflows(self, full: str) -> list[dict]:
        data = await self.get(f"/repos/{full}/actions/workflows", per_page=100)
        return data.get("workflows", [])

    async def list_runs(self, full: str, *, status: str | None = None, per_page: int = 10, workflow_id: str | int | None = None) -> list[dict]:
        params: dict[str, Any] = {"per_page": per_page}
        if status:
            params["status"] = status
        path = f"/repos/{full}/actions/workflows/{workflow_id}/runs" if workflow_id else f"/repos/{full}/actions/runs"
        data = await self.get(path, **params)
        return data.get("workflow_runs", [])

    async def get_run(self, full: str, run_id: int) -> dict:
        return await self.get(f"/repos/{full}/actions/runs/{run_id}")

    async def run_jobs(self, full: str, run_id: int) -> list[dict]:
        data = await self.get(f"/repos/{full}/actions/runs/{run_id}/jobs", per_page=100)
        return data.get("jobs", [])

    async def dispatch_workflow(self, full: str, workflow: str | int, ref: str, inputs: dict | None = None) -> None:
        await self.post(f"/repos/{full}/actions/workflows/{workflow}/dispatches", {"ref": ref, "inputs": inputs or {}})

    async def cancel_run(self, full: str, run_id: int) -> None:
        await self.post(f"/repos/{full}/actions/runs/{run_id}/cancel")

    async def rerun(self, full: str, run_id: int, failed_only: bool = False) -> None:
        suffix = "rerun-failed-jobs" if failed_only else "rerun"
        await self.post(f"/repos/{full}/actions/runs/{run_id}/{suffix}")

    async def run_logs_url(self, full: str, run_id: int) -> str | None:
        resp = await self._request("GET", f"/repos/{full}/actions/runs/{run_id}/logs")
        if resp.status_code in (302, 200):
            return str(resp.url)
        return None

    async def job_log(self, full: str, job_id: int, tail_chars: int = 6000) -> str:
        resp = await self._request("GET", f"/repos/{full}/actions/jobs/{job_id}/logs")
        if resp.status_code != 200:
            raise GitHubError(resp.status_code, "cannot fetch logs")
        text = resp.text
        return text[-tail_chars:] if len(text) > tail_chars else text

    async def scan_running_jobs(self, repos: list[dict], *, limit: int = 40) -> list[dict]:
        """Return in_progress/queued runs across the user's most recently active repos."""
        out: list[dict] = []
        sem = asyncio.Semaphore(6)

        async def one(repo: dict):
            full = repo["full_name"]
            async with sem:
                for st in ("in_progress", "queued"):
                    try:
                        for r in await self.list_runs(full, status=st, per_page=5):
                            out.append({"repo": full, **r})
                    except GitHubError:
                        return

        await asyncio.gather(*(one(r) for r in repos[:limit]))
        return out

    # ---------------------------------------------------------- misc helpers
    async def list_issues(self, full: str, state: str = "open", per_page: int = 10) -> list[dict]:
        return [i for i in await self.get(f"/repos/{full}/issues", state=state, per_page=per_page) if "pull_request" not in i]

    async def list_pulls(self, full: str, state: str = "open", per_page: int = 10) -> list[dict]:
        return await self.get(f"/repos/{full}/pulls", state=state, per_page=per_page)

    async def create_issue(self, full: str, title: str, body: str = "") -> dict:
        return await self.post(f"/repos/{full}/issues", {"title": title, "body": body})

    async def create_pr(self, full: str, title: str, head: str, base: str, body: str = "") -> dict:
        return await self.post(f"/repos/{full}/pulls", {"title": title, "head": head, "base": base, "body": body})

    async def create_release(self, full: str, tag: str, *, name: str = "", body: str = "", draft: bool = False,
                             prerelease: bool = False, target_commitish: str | None = None) -> dict:
        payload: dict[str, Any] = {"tag_name": tag, "name": name or tag, "body": body,
                                   "draft": draft, "prerelease": prerelease}
        if target_commitish:
            payload["target_commitish"] = target_commitish
        return await self.post(f"/repos/{full}/releases", payload)

    async def search_code(self, query: str, *, per_page: int = 10) -> list[dict]:
        return await self.get("/search/code", q=query, per_page=per_page)

    async def list_org_members(self, org: str, per_page: int = 100) -> list[dict]:
        return await self.paginate(f"/orgs/{org}/members", max_pages=3)

    async def list_orgs(self, per_page: int = 100) -> list[dict]:
        return await self.paginate("/user/orgs", max_pages=3)

    async def list_org_repos(self, org: str, per_page: int = 100) -> list[dict]:
        return await self.paginate(f"/orgs/{org}/repos", max_pages=3)

    async def list_org_teams(self, org: str, per_page: int = 100) -> list[dict]:
        return await self.paginate(f"/orgs/{org}/teams", max_pages=3)

    async def gitignore_templates(self) -> list[str]:
        try:
            return await self.get("/gitignore/templates")
        except GitHubError:
            return []

    async def license_templates(self) -> list[dict]:
        try:
            return await self.get("/licenses")
        except GitHubError:
            return []
