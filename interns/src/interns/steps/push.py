"""Push-path operations that mix git subprocess calls with gh pipeline ops.

`push_branch` and `pr_open_for_issue` are the two MCP server tools that need
both a git workspace and GitHub state — they live here rather than in `gh.py`
to keep the pure-gh ops layer free of subprocess/git concerns.
"""

from __future__ import annotations

import re
import subprocess

from ..gh import GhCommandError, InvalidInputError, PushRefusedError, default_branch, pr_create

_PROTECTED_PATHS_RE = r"^\.github/(workflows|scripts)/"


def _git(workspace: str, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=workspace or None, capture_output=True, text=True
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise GhCommandError(detail or f"'git' exited {result.returncode}")
    return result.stdout.strip()


def push_branch(repo: str, workspace: str) -> str:
    """Squash the current branch to one commit and push it to origin.

    Refuses to push main/master, branches with no commits beyond the repo's
    default branch, or commits that touch protected paths
    (.github/workflows/ or .github/scripts/).  Squashing happens before the
    protected-path check so an intermediate-only edit to a protected path is
    collapsed and doesn't trigger a false positive.
    """
    branch = _git(workspace, "rev-parse", "--abbrev-ref", "HEAD")
    if branch in ("main", "master"):
        raise PushRefusedError(f"Refusing to push {branch} directly")

    default = default_branch(repo)
    _git(workspace, "fetch", "origin", default, "--quiet")
    base = _git(workspace, "merge-base", f"origin/{default}", "HEAD")
    head = _git(workspace, "rev-parse", "HEAD")

    if base == head:
        raise PushRefusedError(f"No commits beyond origin/{default} — nothing to push")

    message = _git(workspace, "log", "-1", "--format=%B")
    _git(workspace, "reset", "--soft", base)
    _git(workspace, "commit", "--quiet", "-m", message)

    changed = _git(workspace, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    protected = [p for p in changed.splitlines() if re.search(_PROTECTED_PATHS_RE, p)]
    if protected:
        # Undo the squash so the branch is left in a pushable state after the
        # agent drops the offending edits and retries.
        _git(workspace, "reset", "--soft", head)
        paths = "\n".join(f"  {p}" for p in protected)
        raise PushRefusedError(
            f"Cannot push: changes touch protected paths (drop these edits and push again):\n{paths}"
        )

    _git(workspace, "push", "--force-with-lease", "-u", "origin", branch)
    return f"Branch {branch!r} squashed and pushed to origin"


def pr_open_for_issue(repo: str, workspace: str, issue_number: int, title: str, body: str) -> str:
    """Open a PR from the current branch, automatically appending 'Closes #N' to body.

    Raises InvalidInputError if title contains newlines.
    Raises GhCommandError if HEAD is detached.
    """
    if "\n" in title:
        raise InvalidInputError("Title must be a single line")
    head = _git(workspace, "rev-parse", "--abbrev-ref", "HEAD")
    if head == "HEAD":
        raise GhCommandError("Cannot open a PR from a detached HEAD; check out a branch first")
    full_body = f"{body}\n\nCloses #{issue_number}"
    return pr_create(repo, head, default_branch(repo), title, full_body)
