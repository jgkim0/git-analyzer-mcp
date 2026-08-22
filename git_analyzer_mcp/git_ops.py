"""Low-level git operations used by the MCP server.

Every function here shells out to the system `git` binary via subprocess
(no GitPython dependency) and returns plain JSON-serializable Python
objects (dict / list / str), so they can be used directly as MCP tool
return values and are also easy to unit-test on their own.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Optional

# Fields are separated by \x1f (unit separator) and records by \x1e
# (record separator) so that commit subjects containing spaces/punctuation
# never break the parsing.
_FIELD_SEP = "\x1f"
_RECORD_SEP = "\x1e"
_LOG_FORMAT = _FIELD_SEP.join(
    ["%H", "%h", "%an", "%ae", "%ad", "%s"]
) + _RECORD_SEP


class GitError(RuntimeError):
    """Raised when a git command fails or repo_path is not a git repo."""


def _run_git(repo_path: str, args: list[str], timeout: int = 30) -> str:
    if not os.path.isdir(repo_path):
        raise GitError(f"경로가 존재하지 않거나 디렉터리가 아닙니다: {repo_path}")

    full_args = ["git", "-C", repo_path] + args
    try:
        result = subprocess.run(
            full_args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git 명령이 {timeout}초 내에 끝나지 않았습니다: {' '.join(args)}") from exc
    except FileNotFoundError as exc:
        raise GitError("git 실행 파일을 찾을 수 없습니다. git이 설치되어 있는지 확인하세요.") from exc

    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git 명령 실패 (exit {result.returncode})")

    return result.stdout


def _ensure_repo(repo_path: str) -> None:
    _run_git(repo_path, ["rev-parse", "--is-inside-work-tree"])


def get_recent_commits(repo_path: str, count: int = 10, branch: Optional[str] = None) -> dict:
    """List the most recent commits, newest first."""
    _ensure_repo(repo_path)
    args = ["log", f"-n{max(1, min(count, 200))}", f"--pretty=format:{_LOG_FORMAT}", "--date=iso-strict"]
    if branch:
        args.append(branch)
    out = _run_git(repo_path, args)

    commits = []
    for record in filter(None, out.split(_RECORD_SEP)):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split(_FIELD_SEP)
        if len(parts) != 6:
            continue
        full_hash, short_hash, author_name, author_email, date, subject = parts
        commits.append(
            {
                "hash": full_hash,
                "short_hash": short_hash,
                "author": author_name,
                "email": author_email,
                "date": date,
                "message": subject,
            }
        )
    return {"repo_path": repo_path, "branch": branch or "(current)", "count": len(commits), "commits": commits}


def get_diff(
    repo_path: str,
    ref_a: str,
    ref_b: Optional[str] = None,
    file_path: Optional[str] = None,
    max_chars: int = 20000,
) -> dict:
    """Diff between two refs (commits/branches/tags), or a ref against the working tree."""
    _ensure_repo(repo_path)
    args = ["diff", ref_a]
    if ref_b:
        args.append(ref_b)
    if file_path:
        args += ["--", file_path]
    out = _run_git(repo_path, args)

    truncated = False
    if len(out) > max_chars:
        out = out[:max_chars]
        truncated = True

    return {
        "repo_path": repo_path,
        "ref_a": ref_a,
        "ref_b": ref_b or "(working tree)",
        "file_path": file_path,
        "truncated": truncated,
        "diff": out,
    }


def search_commits(repo_path: str, query: str, max_results: int = 20, branch: Optional[str] = None) -> dict:
    """Search commit messages for a substring/pattern (git log --grep).

    By default this only searches the currently checked-out branch's history,
    same as plain `git log` would. Pass `branch` to search a specific branch,
    or pass branch="--all" to search every branch/tag in the repo.
    """
    _ensure_repo(repo_path)
    args = [
        "log",
        f"-n{max(1, min(max_results, 200))}",
        "-i",
        f"--grep={query}",
        f"--pretty=format:{_LOG_FORMAT}",
        "--date=iso-strict",
    ]
    if branch:
        args.append(branch)
    out = _run_git(repo_path, args)

    commits = []
    for record in filter(None, out.split(_RECORD_SEP)):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split(_FIELD_SEP)
        if len(parts) != 6:
            continue
        full_hash, short_hash, author_name, author_email, date, subject = parts
        commits.append(
            {
                "hash": full_hash,
                "short_hash": short_hash,
                "author": author_name,
                "email": author_email,
                "date": date,
                "message": subject,
            }
        )
    return {
        "repo_path": repo_path,
        "query": query,
        "branch_scope": branch or "(current branch only)",
        "count": len(commits),
        "commits": commits,
    }


def list_branches(repo_path: str) -> dict:
    """List local and remote branches, marking the currently checked-out one."""
    _ensure_repo(repo_path)
    out = _run_git(
        repo_path,
        ["branch", "-a", "--format=%(refname:short)%09%(HEAD)"],
    )
    local, remote = [], []
    current = None
    for line in out.splitlines():
        if not line.strip():
            continue
        name, _, head_marker = line.partition("\t")
        name = name.strip()
        is_current = head_marker.strip() == "*"
        if is_current:
            current = name
        if name.startswith("remotes/"):
            remote.append(name)
        else:
            local.append(name)
    return {"repo_path": repo_path, "current_branch": current, "local_branches": local, "remote_branches": remote}


def get_file_history(repo_path: str, file_path: str, max_results: int = 20) -> dict:
    """List commits that modified a specific file, newest first."""
    _ensure_repo(repo_path)
    args = [
        "log",
        f"-n{max(1, min(max_results, 200))}",
        f"--pretty=format:{_LOG_FORMAT}",
        "--date=iso-strict",
        "--",
        file_path,
    ]
    out = _run_git(repo_path, args)

    commits = []
    for record in filter(None, out.split(_RECORD_SEP)):
        record = record.strip("\n")
        if not record:
            continue
        parts = record.split(_FIELD_SEP)
        if len(parts) != 6:
            continue
        full_hash, short_hash, author_name, author_email, date, subject = parts
        commits.append(
            {
                "hash": full_hash,
                "short_hash": short_hash,
                "author": author_name,
                "email": author_email,
                "date": date,
                "message": subject,
            }
        )
    return {"repo_path": repo_path, "file_path": file_path, "count": len(commits), "commits": commits}


_BLAME_HEADER_RE = re.compile(r"^([0-9a-f]{40}) (\d+) (\d+)")


def blame_file(repo_path: str, file_path: str, ref: Optional[str] = None, max_lines: int = 300) -> dict:
    """Line-by-line blame for a file: which commit/author last touched each line."""
    _ensure_repo(repo_path)
    args = ["blame", "--line-porcelain"]
    if ref:
        args.append(ref)
    args += ["--", file_path]
    out = _run_git(repo_path, args)

    lines = out.split("\n")
    entries = []
    commit_cache: dict[str, dict] = {}
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        m = _BLAME_HEADER_RE.match(line)
        if not m:
            i += 1
            continue

        sha, _orig_line, final_line = m.group(1), int(m.group(2)), int(m.group(3))
        info = dict(commit_cache.get(sha, {}))
        i += 1
        while i < n and not lines[i].startswith("\t"):
            hl = lines[i]
            if hl.startswith("author "):
                info["author"] = hl[len("author "):]
            elif hl.startswith("author-time "):
                try:
                    info["author_time"] = int(hl.split()[1])
                except (IndexError, ValueError):
                    pass
            elif hl.startswith("summary "):
                info["summary"] = hl[len("summary "):]
            i += 1
        commit_cache[sha] = info

        if i < n and lines[i].startswith("\t"):
            content = lines[i][1:]
            i += 1
            entry = {"line": final_line, "commit": sha[:8], "content": content}
            entry.update({k: v for k, v in info.items() if k != "author_time"})
            if "author_time" in info:
                entry["date"] = datetime.fromtimestamp(info["author_time"], tz=timezone.utc).strftime("%Y-%m-%d")
            entries.append(entry)

    entries.sort(key=lambda e: e["line"])
    truncated = len(entries) > max_lines
    if truncated:
        entries = entries[:max_lines]

    return {
        "repo_path": repo_path,
        "file_path": file_path,
        "ref": ref or "HEAD/working-tree",
        "lines_returned": len(entries),
        "truncated": truncated,
        "blame": entries,
    }


def get_status(repo_path: str) -> dict:
    """Working tree status: current branch plus staged/modified/untracked files."""
    _ensure_repo(repo_path)
    branch_out = _run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    status_out = _run_git(repo_path, ["status", "--porcelain=v1"])

    staged, modified, untracked = [], [], []
    for line in status_out.splitlines():
        if not line:
            continue
        code, path = line[:2], line[3:]
        if code == "??":
            untracked.append(path)
        else:
            if code[0] != " " and code[0] != "?":
                staged.append(path)
            if code[1] != " " and code[1] != "?":
                modified.append(path)

    return {
        "repo_path": repo_path,
        "current_branch": branch_out,
        "staged": staged,
        "modified": modified,
        "untracked": untracked,
        "clean": not (staged or modified or untracked),
    }
