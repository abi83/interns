"""GitHub issues MCP server for the interns pipeline."""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
import re
import subprocess
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pipeline import fetch_issue, gh, labels
from pipeline.size import roll_up_size
from pipeline.gh import GhCommandError
from pydantic import BaseModel, Field

mcp = MCPServer("gh-issues")

_REPO = os.environ.get("GITHUB_REPOSITORY", "")
# Used as cwd for git operations so they run against the consumer repo, not
# the server script directory.
_WORKSPACE = os.environ.get("GITHUB_WORKSPACE", "")

_LABELS_JSON = pathlib.Path(__file__).parent.parent.parent / "labels.json"
# Agents are not allowed to push changes to these paths.
_PROTECTED_PATHS_RE = r"^\.github/(workflows|scripts)/"

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InvalidInputError(ValueError):
    """Caller-supplied arguments are malformed or fail validation."""


class PushRefusedError(RuntimeError):
    """push_branch refused: protected branch, nothing to push, or a protected path."""


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class InlineComment(BaseModel):
    path: str = Field(description="File path relative to repo root.")
    line: int = Field(description="Line number in the file.", ge=1)
    body: str = Field(description="Comment text.", min_length=1, max_length=10000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _git(*args: str) -> str:
    """Run `git` in the consumer workspace; re-raise failures with stderr so
    agents see why. `gh` calls go through the shared `pipeline.gh` client."""
    result = subprocess.run(["git", *args], cwd=_WORKSPACE or None, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise GhCommandError(detail or f"'git' exited {result.returncode}")
    return result.stdout.strip()


def _load_label_names() -> list[str]:
    try:
        data = json.loads(_LABELS_JSON.read_text())
        return [entry["name"] for entry in data.get("labels", [])]
    except (OSError, KeyError, json.JSONDecodeError):
        return []


# Computed once at import time, not re-read per call: labels.json only changes
# via a separate PR to this repo, never mid-process, so a stale in-process
# cache for the lifetime of one server run is an acceptable, intentional trade-off.
_KNOWN_LABELS = _load_label_names()
_LABEL_DESCRIPTION = (
    "Label to filter by. Pass '' (or omit) to list all open issues. "
    + (f"Valid labels: {', '.join(_KNOWN_LABELS)}." if _KNOWN_LABELS else "")
)

# ---------------------------------------------------------------------------
# Issue read tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_issues(
    label: Annotated[str, Field(description=_LABEL_DESCRIPTION)] = "",
) -> str:
    """List open issues in the repository.

    Returns a JSON array; each element has number, title, labels, state.
    """
    return json.dumps(gh.issue_list(_REPO, label=label))


@mcp.tool()
def view_issue(
    issue_number: Annotated[int, Field(description="Issue number to fetch.")],
) -> str:
    """Get full details of one issue: number, title, body, labels, state, comments,
    and GitHub relationships (parent, sub-issues, blockedBy, blocking).

    Returns a flat JSON object — labels is a list of strings, comments is a list
    of {author, created_at, body} objects.
    """
    return json.dumps(dataclasses.asdict(fetch_issue.fetch_issue(_REPO, issue_number)))


# ---------------------------------------------------------------------------
# Issue write tools
# ---------------------------------------------------------------------------


@mcp.tool()
def comment_issue(
    issue_number: Annotated[int, Field(description="Issue number to comment on.")],
    body: Annotated[str, Field(description="Comment body (markdown).", min_length=1, max_length=10000)],
) -> str:
    """Post a comment on an issue."""
    return gh.issue_comment(_REPO, issue_number, body) or f"Comment posted on issue #{issue_number}"


@mcp.tool()
def edit_issue(
    issue_number: Annotated[int, Field(description="Issue number.")],
    body: Annotated[str, Field(description="New issue body (markdown).", min_length=10, max_length=10000)],
    title: Annotated[
        str | None,
        Field(description="New issue title (single line). Omit to leave the title unchanged.", min_length=5, max_length=300),
    ] = None,
) -> str:
    """Set the body of an issue, and optionally its title.

    Always pass the full rewritten body. Pass title only when it needs
    correcting — omit it to leave the existing title in place.
    """
    if title is not None and "\n" in title:
        raise InvalidInputError("Title must be a single line")
    output = gh.issue_edit(_REPO, issue_number, body=body, title=title)
    updated = ["body"] + (["title"] if title is not None else [])
    return output or f"Updated {' and '.join(updated)} on issue #{issue_number}"


@mcp.tool()
def edit_issue_labels(
    issue_number: Annotated[int, Field(description="Issue number.")],
    add_labels: Annotated[list[str] | None, Field(description="Labels to add.")] = None,
    remove_labels: Annotated[list[str] | None, Field(description="Labels to remove.")] = None,
) -> str:
    """Add or remove labels on an issue.

    Only labels that exist in the repository are accepted. Pass an empty list
    to skip adding or removing.
    """
    add_labels = add_labels or []
    remove_labels = remove_labels or []
    if not add_labels and not remove_labels:
        return "Nothing to do"

    valid = set(gh.label_names(_REPO))

    unknown_add = [lbl for lbl in add_labels if lbl not in valid]
    unknown_remove = [lbl for lbl in remove_labels if lbl not in valid]
    if unknown_add or unknown_remove:
        msgs = []
        if unknown_add:
            msgs.append(f"Labels don't exist, not added: {', '.join(unknown_add)}")
        if unknown_remove:
            msgs.append(f"Labels don't exist, not removed: {', '.join(unknown_remove)}")
        raise InvalidInputError("\n".join(msgs))

    labels.edit_issue_labels_strict(_REPO, issue_number, add=add_labels, remove=remove_labels)
    parts = []
    if add_labels:
        parts.append(f"Added: {', '.join(add_labels)}")
    if remove_labels:
        parts.append(f"Removed: {', '.join(remove_labels)}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# PR write tools
# ---------------------------------------------------------------------------


@mcp.tool()
def comment_pr(
    pr_number: Annotated[int, Field(description="PR number to comment on.")],
    body: Annotated[str, Field(description="Comment body (markdown).", min_length=1, max_length=10000)],
) -> str:
    """Post a comment on a pull request."""
    return gh.pr_comment(_REPO, pr_number, body) or f"Comment posted on PR #{pr_number}"


@mcp.tool()
def open_pr(
    issue_number: Annotated[int, Field(description="Issue number this PR closes.")],
    title: Annotated[str, Field(description="PR title (single line, Conventional Commit format).", min_length=5, max_length=300)],
    body: Annotated[str, Field(description="PR body (markdown). 'Closes #N' is appended automatically.", min_length=10, max_length=10000)],
) -> str:
    """Open a PR from the current branch.

    Appends 'Closes #<issue_number>' to the body automatically so the PR is
    linked to the issue via GitHub's closing-reference mechanism.
    """
    full_body = f"{body}\n\nCloses #{issue_number}"
    head = _git("rev-parse", "--abbrev-ref", "HEAD")
    if head == "HEAD":
        raise GhCommandError("Cannot open a PR from a detached HEAD; check out a branch first")
    return gh.pr_create(_REPO, head, gh.default_branch(_REPO), title, full_body)


@mcp.tool()
def submit_pr_review(
    pr_number: Annotated[int, Field(description="PR number.")],
    event: Annotated[Literal["APPROVE", "REQUEST_CHANGES"], Field(description="Review verdict.")],
    body: Annotated[str, Field(description="Review summary comment.", min_length=10, max_length=10000)],
    comments: Annotated[
        list[InlineComment] | None,
        Field(description='Inline comments per changed line. Empty list or omit for APPROVE.'),
    ] = None,
) -> str:
    """Submit a formal PR review (verdict + optional inline comments) atomically."""
    if event not in ("APPROVE", "REQUEST_CHANGES"):
        raise InvalidInputError("event must be APPROVE or REQUEST_CHANGES")
    payload = {"event": event, "body": body, "comments": [c.model_dump() for c in (comments or [])]}
    result = gh.api(f"repos/{_REPO}/pulls/{pr_number}/reviews", method="POST", input_json=json.dumps(payload))
    return json.dumps(result)


# ---------------------------------------------------------------------------
# Branch / push tools
# ---------------------------------------------------------------------------


@mcp.tool()
def push_branch() -> str:
    """Squash the current branch to one commit and push it to origin.

    Refuses to push main/master, branches with no commits beyond origin/main,
    or commits that touch protected paths (.github/workflows/ or .github/scripts/).
    Squashing happens before the protected-path check so an intermediate-only
    edit to a protected path is collapsed and doesn't trigger a false positive.
    """
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if branch in ("main", "master"):
        raise PushRefusedError(f"Refusing to push {branch} directly")

    _git("fetch", "origin", "main", "--quiet")
    base = _git("merge-base", "origin/main", "HEAD")
    head = _git("rev-parse", "HEAD")

    if base == head:
        raise PushRefusedError("No commits beyond origin/main — nothing to push")

    message = _git("log", "-1", "--format=%B")
    _git("reset", "--soft", base)
    _git("commit", "--quiet", "-m", message)

    changed = _git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    protected = [p for p in changed.splitlines() if re.search(_PROTECTED_PATHS_RE, p)]
    if protected:
        paths = "\n".join(f"  {p}" for p in protected)
        raise PushRefusedError(
            f"Cannot push: changes touch protected paths (drop these edits and push again):\n{paths}"
        )

    _git("push", "--force-with-lease", "-u", "origin", branch)
    return f"Branch {branch!r} squashed and pushed to origin"


# ---------------------------------------------------------------------------
# Outcome tools — apply pipeline lifecycle label transitions directly,
# so refiner/estimator need no Write access and no marker files on disk.
# ---------------------------------------------------------------------------


@mcp.tool()
def apply_refinement_outcome(
    issue_number: Annotated[int, Field(description="Issue number.")],
    outcome: Annotated[Literal["refined", "needs-attention"], Field(description="Refinement outcome.")],
    type_label: Annotated[
        Literal[labels.TYPE_CODING_TASK, labels.TYPE_BUG, labels.TYPE_SPIKE] | None,
        Field(description="Required when outcome='refined'. The type label for this issue."),
    ] = None,
) -> str:
    """Apply the lifecycle label transition after refinement.

    refined       → requires type_label; removes status:needs-refinement and
                    status:needs-attention, adds status:refined and the type label
                    (which triggers the estimate job).
    needs-attention → removes status:needs-refinement, adds status:needs-attention.
    """
    if outcome == "refined":
        if type_label is None:
            raise InvalidInputError("type_label is required when outcome='refined'")
        transition = labels.refined(type_label)
    elif outcome == "needs-attention":
        transition = labels.refinement_needs_attention()
    else:
        raise InvalidInputError("outcome must be 'refined' or 'needs-attention'")

    labels.apply_transition(_REPO, issue_number, transition)
    return f"Refinement outcome '{outcome}' applied to issue #{issue_number}"


@mcp.tool()
def apply_estimation_outcome(
    issue_number: Annotated[int, Field(description="Issue number.")],
    outcome: Annotated[Literal["estimated", "needs-attention"], Field(description="Estimation outcome.")],
    blast_radius: Annotated[
        Literal["Low", "Mid", "High"] | None,
        Field(description="Risk of breaking existing functionality. Required when outcome='estimated'."),
    ] = None,
    touch: Annotated[
        Literal["Low", "Mid", "High"] | None,
        Field(description="Number of files/components touched. Required when outcome='estimated'."),
    ] = None,
    human_involvement: Annotated[
        Literal["Low", "Mid", "High"] | None,
        Field(description="Expected back-and-forth with the owner. Required when outcome='estimated'."),
    ] = None,
    review_overhead: Annotated[
        Literal["Low", "Mid", "High"] | None,
        Field(description="Reviewer effort. Required when outcome='estimated'."),
    ] = None,
) -> str:
    """Apply the lifecycle label transition after estimation.

    estimated     → rolls the four Low|Mid|High scores into a size:* label,
                    then removes status:refined and status:needs-attention,
                    adds status:estimated and the computed size:* label.
    needs-attention → removes status:refined, adds status:needs-attention.
    """
    if outcome == "estimated":
        if None in (blast_radius, touch, human_involvement, review_overhead):
            raise InvalidInputError(
                "blast_radius, touch, human_involvement, and review_overhead are all required when outcome='estimated'"
            )
        size = roll_up_size(blast_radius, touch, human_involvement, review_overhead)  # type: ignore[arg-type]
        transition = labels.estimated(size)
    elif outcome == "needs-attention":
        transition = labels.estimation_needs_attention()
    else:
        raise InvalidInputError("outcome must be 'estimated' or 'needs-attention'")

    labels.apply_transition(_REPO, issue_number, transition)

    if outcome == "estimated":
        return f"Estimation outcome 'estimated' applied to issue #{issue_number} ({labels.size_label(size)})"
    return f"Estimation outcome 'needs-attention' applied to issue #{issue_number}"


if __name__ == "__main__":
    mcp.run()
