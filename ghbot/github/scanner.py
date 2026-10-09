"""Account scan: identity, access level, repos, running jobs, rate-limit budget."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .access import AccessLevel, classify_access
from .client import GitHubClient, GitHubError


@dataclass
class ScanResult:
    login: str = ""
    name: str = ""
    plan: str = ""
    public_repos: int = 0
    total_private: int = 0
    followers: int = 0
    scopes: list[str] | None = None
    fine_grained: bool = False
    level: AccessLevel | None = None
    repos: list[dict] = field(default_factory=list)
    orgs: list[str] = field(default_factory=list)
    running: list[dict] = field(default_factory=list)
    rate: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


async def scan_account(gh: GitHubClient, *, progress=None) -> ScanResult:
    res = ScanResult()

    async def say(msg: str):
        if progress:
            await progress(msg)

    await say("identity")
    me = await gh.me()
    res.login = me.get("login", "")
    res.name = me.get("name") or ""
    res.plan = (me.get("plan") or {}).get("name", "")
    res.public_repos = me.get("public_repos", 0)
    res.total_private = me.get("total_private_repos", 0) or 0
    res.followers = me.get("followers", 0)

    res.scopes = gh.scopes
    if gh.scopes is None:
        res.fine_grained = True
        probe = await gh.probe_fine_grained(res.login)
        res.level = classify_access(None, fine_grained_probe=probe)
    else:
        res.level = classify_access(gh.scopes)

    await say("repos")
    repos_task = asyncio.create_task(gh.list_repos(max_pages=5))
    orgs_task = asyncio.create_task(gh.list_orgs())
    rate_task = asyncio.create_task(gh.rate_limit_status())

    for name, task in (("repos", repos_task), ("orgs", orgs_task), ("rate", rate_task)):
        try:
            val = await task
        except GitHubError as e:
            res.errors.append(f"{name}: {e.message}")
            continue
        if name == "repos":
            res.repos = val
        elif name == "orgs":
            res.orgs = [o.get("login", "") for o in val]
        else:
            res.rate = (val or {}).get("resources", {}).get("core", {})

    await say("actions")
    try:
        res.running = await gh.scan_running_jobs(res.repos, limit=30)
    except GitHubError as e:
        res.errors.append(f"actions: {e.message}")
    return res
