"""github_api — one tool, many actions, authenticated as the Telegram user.

Wraps ``GitHubClient`` so the agent gets retry/rate-limit handling for free and
never touches the raw token.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...github.client import GitHubError
from ...github.zipflow import detect_secrets_in_texts
from .context import ToolContext

ACTIONS = [
    "me", "list_repos", "get_repo", "create_repo", "update_repo", "delete_repo", "list_branches", "tree",
    "get_file", "put_file", "commit_tree", "upload_dir",
    "list_secrets", "set_secret", "delete_secret", "detect_secrets", "list_variables", "set_variable",
    "list_workflows", "list_runs", "get_run", "run_jobs", "job_log", "dispatch", "cancel_run", "rerun",
    "list_issues", "create_issue", "create_pr", "create_release", "search_code",
    "list_orgs", "list_org_members", "list_org_repos", "list_org_teams",
    "list_pulls", "rate_limit", "raw",
]

SCHEMA = {
    "name": "github_api",
    "description": (
        "Call the GitHub API as the current user (token already attached; never ask for it). Actions: "
        + ", ".join(ACTIONS) + ". "
        "repo is 'owner/name'. commit_tree pushes many files in ONE commit: files={path: text}, replace_all=true "
        "replaces the whole tree. upload_dir does the same from a local directory. put_file writes a single file "
        "(auto-detects sha for updates). raw: method+path(+body) for anything not covered. Destructive actions "
        "(delete_repo, delete_secret, replace_all=true, update_repo private→public) need explicit user confirmation "
        "earlier in the conversation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ACTIONS},
            "repo": {"type": "string"},
            "name": {"type": "string"},
            "value": {"type": "string"},
            "path": {"type": "string"},
            "ref": {"type": "string"},
            "branch": {"type": "string"},
            "message": {"type": "string"},
            "content": {"type": "string"},
            "files": {"type": "object", "additionalProperties": {"type": "string"}},
            "local_dir": {"type": "string"},
            "replace_all": {"type": "boolean"},
            "private": {"type": "boolean"},
            "description": {"type": "string"},
            "auto_init": {"type": "boolean"},
            "org": {"type": "string"},
            "fields": {"type": "object"},
            "status": {"type": "string"},
            "run_id": {"type": "integer"},
            "job_id": {"type": "integer"},
            "workflow": {"type": "string", "description": "workflow file name or id"},
            "inputs": {"type": "object"},
            "failed_only": {"type": "boolean"},
            "title": {"type": "string"},
            "body": {"type": "string"},
            "head": {"type": "string"},
            "base": {"type": "string"},
            "tag": {"type": "string"},
            "draft": {"type": "boolean"},
            "prerelease": {"type": "boolean"},
            "query": {"type": "string"},
            "org": {"type": "string"},
            "method": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["action"],
    },
}

_SKIP = {".git", "node_modules", "__pycache__", ".venv", "data", ".ghbot_logs"}


def _slim_repo(r: dict) -> dict:
    return {k: r.get(k) for k in ("full_name", "private", "default_branch", "description", "html_url", "updated_at",
                                  "stargazers_count", "open_issues_count", "archived", "fork")}


def _slim_run(r: dict) -> dict:
    return {k: r.get(k) for k in ("id", "run_number", "name", "status", "conclusion", "head_branch", "event",
                                  "created_at", "updated_at", "html_url")}


async def handle(ctx: ToolContext, args: dict) -> str:
    gh = ctx.gh
    if gh is None:
        return json.dumps({"error": "no GitHub token configured for this user"})
    a = args.get("action")
    repo = args.get("repo", "")
    try:
        if a == "me":
            me = await gh.me()
            return json.dumps({"login": me.get("login"), "name": me.get("name"), "scopes": gh.scopes})
        if a == "rate_limit":
            return json.dumps((await gh.rate_limit_status()).get("resources", {}).get("core", {}))
        if a == "list_repos":
            repos = await gh.list_repos(max_pages=3)
            return json.dumps([_slim_repo(r) for r in repos[: int(args.get("limit") or 60)]], ensure_ascii=False)
        if a == "get_repo":
            return json.dumps(_slim_repo(await gh.get_repo(repo)), ensure_ascii=False)
        if a == "create_repo":
            r = await gh.create_repo(name=args["name"], private=bool(args.get("private", True)),
                                     description=args.get("description", ""), auto_init=bool(args.get("auto_init", True)),
                                     org=args.get("org"))
            return json.dumps(_slim_repo(r), ensure_ascii=False)
        if a == "update_repo":
            return json.dumps(_slim_repo(await gh.update_repo(repo, **(args.get("fields") or {}))), ensure_ascii=False)
        if a == "delete_repo":
            await gh.delete_repo(repo)
            return json.dumps({"success": True, "deleted": repo})
        if a == "list_branches":
            return json.dumps([b["name"] for b in await gh.list_branches(repo)])
        if a == "tree":
            ref = args.get("ref") or (await gh.get_repo(repo))["default_branch"]
            tree = await gh.get_tree(repo, ref)
            paths = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
            return json.dumps({"ref": ref, "count": len(paths), "truncated": tree.get("truncated", False), "paths": paths[:800]})
        if a == "get_file":
            text = await gh.get_file_text(repo, args["path"], args.get("ref"))
            return json.dumps({"path": args["path"], "content": text} if text is not None else {"error": "not found"}, ensure_ascii=False)
        if a == "put_file":
            r = await gh.upsert_file(repo, args["path"], (args.get("content") or "").encode(), args.get("message") or f"Update {args['path']}", args.get("branch"))
            return json.dumps({"success": True, "sha": r.get("commit", {}).get("sha"), "url": r.get("content", {}).get("html_url")})
        if a in ("commit_tree", "upload_dir"):
            if a == "commit_tree":
                files = {p: (c if isinstance(c, str) else json.dumps(c)).encode() for p, c in (args.get("files") or {}).items()}
            else:
                root = ctx.resolve(args["local_dir"])
                files = {}
                for p in root.rglob("*"):
                    rel = p.relative_to(root)
                    if p.is_file() and not any(part in _SKIP for part in rel.parts) and len(files) < 3000:
                        files[rel.as_posix()] = p.read_bytes()
            if not files:
                return json.dumps({"error": "no files"})
            branch = args.get("branch") or (await gh.get_repo(repo))["default_branch"]

            async def prog(msg):
                if ctx.notify:
                    await ctx.notify(f"📤 {msg}")

            commit = await gh.commit_tree(repo, branch, files, args.get("message") or "Upload via GITHUB_AI",
                                          replace_all=bool(args.get("replace_all")), progress=prog)
            return json.dumps({"success": True, "files": len(files), "sha": commit["sha"], "url": commit.get("html_url")})
        if a == "list_secrets":
            return json.dumps([{"name": s["name"], "updated_at": s.get("updated_at")} for s in await gh.list_secrets(repo)])
        if a == "set_secret":
            await gh.set_secret(repo, args["name"], args.get("value", ""))
            return json.dumps({"success": True, "name": args["name"]})
        if a == "delete_secret":
            await gh.delete_secret(repo, args["name"])
            return json.dumps({"success": True})
        if a == "detect_secrets":
            r = await gh.get_repo(repo)
            tree = await gh.get_tree(repo, r["default_branch"])
            texts = {}
            for t in tree.get("tree", []):
                if t.get("type") == "blob" and t["path"].startswith(".github/workflows/") and t["path"].endswith((".yml", ".yaml")):
                    txt = await gh.get_file_text(repo, t["path"])
                    if txt:
                        texts[t["path"]] = txt
            needed = detect_secrets_in_texts(texts)
            existing = {s["name"] for s in await gh.list_secrets(repo)}
            return json.dumps({"workflows": list(texts), "referenced": needed, "missing": [n for n in needed if n not in existing]})
        if a == "list_variables":
            return json.dumps(await gh.list_variables(repo))
        if a == "set_variable":
            await gh.set_variable(repo, args["name"], args.get("value", ""))
            return json.dumps({"success": True})
        if a == "list_workflows":
            return json.dumps([{"id": w["id"], "name": w["name"], "path": w["path"], "state": w["state"]} for w in await gh.list_workflows(repo)])
        if a == "list_runs":
            runs = await gh.list_runs(repo, status=args.get("status"), per_page=int(args.get("limit") or 10), workflow_id=args.get("workflow"))
            return json.dumps([_slim_run(r) for r in runs])
        if a == "get_run":
            return json.dumps(_slim_run(await gh.get_run(repo, int(args["run_id"]))))
        if a == "run_jobs":
            jobs = await gh.run_jobs(repo, int(args["run_id"]))
            return json.dumps([{"id": j["id"], "name": j["name"], "status": j["status"], "conclusion": j.get("conclusion"),
                                "steps": [{"name": s["name"], "conclusion": s.get("conclusion")} for s in j.get("steps", []) if s.get("conclusion") not in (None, "success", "skipped")]} for j in jobs])
        if a == "job_log":
            return json.dumps({"log_tail": await gh.job_log(repo, int(args["job_id"]), 12_000)})
        if a == "dispatch":
            ref = args.get("ref") or (await gh.get_repo(repo))["default_branch"]
            await gh.dispatch_workflow(repo, args["workflow"], ref, args.get("inputs"))
            return json.dumps({"success": True, "ref": ref})
        if a == "cancel_run":
            await gh.cancel_run(repo, int(args["run_id"]))
            return json.dumps({"success": True})
        if a == "rerun":
            await gh.rerun(repo, int(args["run_id"]), bool(args.get("failed_only")))
            return json.dumps({"success": True})
        if a == "list_issues":
            return json.dumps([{"number": i["number"], "title": i["title"], "state": i["state"], "url": i["html_url"]} for i in await gh.list_issues(repo)])
        if a == "create_issue":
            i = await gh.create_issue(repo, args["title"], args.get("body", ""))
            return json.dumps({"number": i["number"], "url": i["html_url"]})
        if a == "create_pr":
            pr = await gh.create_pr(repo, args["title"], args["head"], args["base"], args.get("body", ""))
            return json.dumps({"number": pr["number"], "url": pr["html_url"], "state": pr.get("state")})
        if a == "create_release":
            rel = await gh.create_release(repo, args["tag"], name=args.get("name", ""), body=args.get("body", ""),
                                         draft=bool(args.get("draft")), prerelease=bool(args.get("prerelease")))
            return json.dumps({"tag": rel.get("tag_name"), "url": rel.get("html_url"), "draft": rel.get("draft")})
        if a == "search_code":
            res = await gh.search_code(args.get("query", ""), per_page=int(args.get("limit") or 10))
            return json.dumps([{"repo": i.get("repository", {}).get("full_name"), "path": i.get("path"),
                                "url": i.get("html_url")} for i in res.get("items", [])], ensure_ascii=False)
        if a == "list_orgs":
            return json.dumps([{"login": o["login"], "url": o["url"]} for o in await gh.list_orgs()])
        if a == "list_org_members":
            return json.dumps([{"login": m["login"]} for m in await gh.list_org_members(args["org"])])
        if a == "list_org_repos":
            return json.dumps([_slim_repo(r) for r in await gh.list_org_repos(args["org"])], ensure_ascii=False)
        if a == "list_org_teams":
            return json.dumps([{"name": t["name"], "slug": t["slug"], "privacy": t.get("privacy")} for t in await gh.list_org_teams(args["org"])])
        if a == "list_pulls":
            return json.dumps([{"number": p["number"], "title": p["title"], "state": p["state"], "url": p["html_url"]} for p in await gh.list_pulls(repo)])
        if a == "raw":
            method = (args.get("method") or "GET").upper()
            path = args.get("path", "")
            if not path.startswith("/"):
                return json.dumps({"error": "path must start with /"})
            data = await gh._json(method, path, json=args.get("body") if method != "GET" else None)
            return json.dumps(data, ensure_ascii=False)[:20000]
        return json.dumps({"error": f"unknown action {a}", "actions": ACTIONS})
    except GitHubError as e:
        return json.dumps({"error": e.message, "status": e.status})
    except KeyError as e:
        return json.dumps({"error": f"missing argument {e}"})
