---
name: repo-upload
description: "Upload a folder/ZIP/set of files into a GitHub repo in ONE commit via the Git Data API, with wipe-or-merge semantics."
---

# Repo upload (single commit, Git Data API)

## When to use
User wants files pushed into a repository without cloning: "put this project in repo X", "replace everything in repo", "upload the workspace".

## Procedure
1. Confirm target `owner/repo`, branch (default: repo `default_branch`), and whether to **replace all** existing files or **merge on top**. Replacing is destructive — require explicit confirmation.
2. Build the file map `{path: text}`. Skip `.git/`, `node_modules/`, `__MACOSX/`, `__pycache__/`, `.DS_Store`. Reject paths with `..`.
3. If every path shares one root folder, ask whether to keep the folder or upload its contents.
4. Call `github_api(action="commit_tree", repo=..., branch=..., files=..., message=..., replace_all=...)`. It creates blobs → tree → commit → updates the ref. One commit, atomic. For files already on disk use `github_api(action="upload_dir", repo=..., local_dir=...)`.
5. Scan `.github/workflows/*.yml` in the uploaded files for `${{ secrets.NAME }}`; compare with `github_api(action="list_secrets")` and offer to set the missing ones (`set_secret`).
6. Report commit SHA + URL.

## Pitfalls
- Empty repos (no commits) have no ref: `commit_tree` handles this by creating the ref.
- Max ~95MB per upload, 3000 files, 50MB per file.
- A secret value must never appear in chat/log; GitHub only returns names.
