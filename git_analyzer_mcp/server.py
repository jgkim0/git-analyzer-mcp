"""MCP server exposing read-only git repository inspection tools.

Run directly for local testing:
    python -m git_analyzer_mcp.server

Or, once installed (pip install -e .), via the console script:
    git-analyzer-mcp
"""

from __future__ import annotations

from typing import Optional

from mcp.server import MCPServer

from . import git_ops
from .git_ops import GitError

# The name shows up in MCP clients (e.g. Claude Desktop's server list).
mcp = MCPServer("git-analyzer")


def _safe(fn, *args, **kwargs) -> dict:
    """Run a git_ops function and turn GitError into a structured error dict
    instead of letting the exception crash the tool call."""
    try:
        return fn(*args, **kwargs)
    except GitError as exc:
        return {"error": str(exc)}


@mcp.tool()
def list_recent_commits(repo_path: str, count: int = 10, branch: Optional[str] = None) -> dict:
    """List the most recent commits in a git repository, newest first.

    Args:
        repo_path: Absolute path to the local git repository.
        count: How many commits to return (max 200).
        branch: Optional branch/ref name; defaults to the currently checked-out branch.
    """
    return _safe(git_ops.get_recent_commits, repo_path, count, branch)


@mcp.tool()
def get_diff(
    repo_path: str,
    ref_a: str,
    ref_b: Optional[str] = None,
    file_path: Optional[str] = None,
) -> dict:
    """Show the diff between two commits/branches/tags, or between one ref and the working tree.

    Args:
        repo_path: Absolute path to the local git repository.
        ref_a: First ref (commit hash, branch name, or tag).
        ref_b: Second ref to compare against. If omitted, diffs ref_a against the working tree.
        file_path: Optional path to restrict the diff to a single file.
    """
    return _safe(git_ops.get_diff, repo_path, ref_a, ref_b, file_path)


@mcp.tool()
def search_commits(
    repo_path: str,
    query: str,
    max_results: int = 20,
    branch: Optional[str] = None,
) -> dict:
    """Search commit messages for a keyword or pattern (case-insensitive).

    Args:
        repo_path: Absolute path to the local git repository.
        query: Text to search for in commit messages.
        max_results: Maximum number of matching commits to return (max 200).
        branch: Branch/ref to search. Pass "--all" to search every branch and tag.
            Defaults to only the currently checked-out branch.
    """
    return _safe(git_ops.search_commits, repo_path, query, max_results, branch)


@mcp.tool()
def list_branches(repo_path: str) -> dict:
    """List local and remote branches, and identify the currently checked-out branch.

    Args:
        repo_path: Absolute path to the local git repository.
    """
    return _safe(git_ops.list_branches, repo_path)


@mcp.tool()
def get_file_history(repo_path: str, file_path: str, max_results: int = 20) -> dict:
    """List the commits that modified a specific file, newest first.

    Args:
        repo_path: Absolute path to the local git repository.
        file_path: Path to the file, relative to the repository root.
        max_results: Maximum number of commits to return (max 200).
    """
    return _safe(git_ops.get_file_history, repo_path, file_path, max_results)


@mcp.tool()
def blame_file(repo_path: str, file_path: str, ref: Optional[str] = None) -> dict:
    """Line-by-line blame for a file: which commit and author last touched each line.

    Args:
        repo_path: Absolute path to the local git repository.
        file_path: Path to the file, relative to the repository root.
        ref: Optional commit/branch to blame at, instead of the current working tree.
    """
    return _safe(git_ops.blame_file, repo_path, file_path, ref)


@mcp.tool()
def get_status(repo_path: str) -> dict:
    """Show working tree status: current branch, staged/modified/untracked files.

    Args:
        repo_path: Absolute path to the local git repository.
    """
    return _safe(git_ops.get_status, repo_path)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
