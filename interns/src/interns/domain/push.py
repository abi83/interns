"""Push-path operations that mix git subprocess calls with gh ops, so they live outside
the pure `interns.gh` layer."""

from __future__ import annotations

import re
import subprocess

from ..gh import (
    GhCommandError,
    InvalidInputError,
    PushRefusedError,
    default_branch,
    pr_create,
    pr_for_head,
    pr_ready,
    pr_update,
)

PROTECTED_PATHS_RE = r"^\.github/(workflows|scripts)/"


def git(workspace: str, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=workspace or None, capture_output=True, text=True
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise GhCommandError(detail or f"'git' exited {result.returncode}")
    return result.stdout.strip()


def unprotected_branch(workspace: str) -> str:
    branch = git(workspace, "rev-parse", "--abbrev-ref", "HEAD")
    if branch in ("main", "master"):
        raise PushRefusedError(f"Refusing to push {branch} directly")
    return branch


def fork_point(repo: str, workspace: str) -> tuple[str, str]:
    """(default branch, merge-base of HEAD with its fresh origin copy)."""
    default = default_branch(repo)
    git(workspace, "fetch", "origin", default, "--quiet")
    return default, git(workspace, "merge-base", f"origin/{default}", "HEAD")


def push_branch(repo: str, workspace: str) -> str:
    """Squash the current branch to one commit and push it to origin.

    Refuses to push main/master, branches with no commits beyond the repo's
    default branch, or commits that touch protected paths
    (.github/workflows/ or .github/scripts/).  Squashing happens before the
    protected-path check so an intermediate-only edit to a protected path is
    collapsed and doesn't trigger a false positive.
    """
    branch = unprotected_branch(workspace)
    default, base = fork_point(repo, workspace)
    head = git(workspace, "rev-parse", "HEAD")

    if base == head:
        raise PushRefusedError(f"No commits beyond origin/{default} — nothing to push")

    message = git(workspace, "log", "-1", "--format=%B")
    git(workspace, "reset", "--soft", base)
    git(workspace, "commit", "--quiet", "-m", message)

    changed = git(workspace, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    protected = [p for p in changed.splitlines() if re.search(PROTECTED_PATHS_RE, p)]
    if protected:
        # Undo the squash so the agent can drop the offending edits and retry.
        git(workspace, "reset", "--soft", head)
        paths = "\n".join(f"  {p}" for p in protected)
        raise PushRefusedError(
            f"Cannot push: changes touch protected paths (drop these edits and push again):\n{paths}"
        )

    git(workspace, "push", "--force-with-lease", "-u", "origin", branch)
    return f"Branch {branch!r} squashed and pushed to origin"


def pr_open_for_issue(repo: str, workspace: str, issue_number: int, title: str, body: str) -> str:
    """Open a PR from the current branch, automatically appending 'Closes #N' to body.

    A branch that already has an open PR (e.g. a failed run's draft) gets
    that PR updated and marked ready instead of a second one.

    Raises InvalidInputError if title contains newlines.
    Raises GhCommandError if HEAD is detached.
    """
    if "\n" in title:
        raise InvalidInputError("Title must be a single line")
    head = git(workspace, "rev-parse", "--abbrev-ref", "HEAD")
    if head == "HEAD":
        raise GhCommandError("Cannot open a PR from a detached HEAD; check out a branch first")
    full_body = f"{body}\n\nCloses #{issue_number}"
    existing = pr_for_head(repo, head)
    if existing is None:
        return pr_create(repo, head, default_branch(repo), title, full_body)
    pr_update(repo, existing["number"], title=title, body=full_body)
    if existing["isDraft"]:
        pr_ready(repo, existing["number"])
    return existing["url"]
