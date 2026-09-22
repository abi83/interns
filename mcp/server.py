"""GitHub issues MCP server for the interns pipeline."""

from __future__ import annotations

import dataclasses
import json
import os
import pathlib
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from interns import gh
from interns.steps import fetch_issue, labels, push
from interns.gh import GhCommandError, InvalidInputError, PushRefusedError  # noqa: F401 — re-exported for callers
from pydantic import BaseModel, Field

mcp = MCPServer("gh-issues")

_REPO = os.environ.get("GITHUB_REPOSITORY", "")
_WORKSPACE = os.environ.get("GITHUB_WORKSPACE", "")

_LABELS_JSON = pathlib.Path(__file__).parent.parent / ".github" / "labels.json"

# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class InlineComment(BaseModel):
    path: str = Field(description="File path relative to repo root.")
    line: int = Field(description="Line number in the file.", ge=1)
    body: str = Field(description="Comment text.", min_length=1, max_length=10000)


# ---------------------------------------------------------------------------
# Label description helper (computed once at import)
# ---------------------------------------------------------------------------


def _load_label_names() -> list[str]:
    data = json.loads(_LABELS_JSON.read_text())
    return [entry["name"] for entry in data["labels"]]


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
    return gh.issue_edit_validated(_REPO, issue_number, body=body, title=title)


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
    return labels.edit_issue_labels_validated(_REPO, issue_number, add=add_labels, remove=remove_labels)


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
    return push.pr_open_for_issue(_REPO, _WORKSPACE, issue_number, title, body)


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
    comment_dicts = [c.model_dump() for c in (comments or [])]
    return json.dumps(gh.pr_submit_review(_REPO, pr_number, event, body, comment_dicts))


# ---------------------------------------------------------------------------
# Branch / push tools
# ---------------------------------------------------------------------------


@mcp.tool()
def push_branch() -> str:
    """Squash the current branch to one commit and push it to origin.

    Refuses to push main/master, branches with no commits beyond origin's default branch,
    or commits that touch protected paths (.github/workflows/ or .github/scripts/).
    Squashing happens before the protected-path check so an intermediate-only
    edit to a protected path is collapsed and doesn't trigger a false positive.
    """
    return push.push_branch(_REPO, _WORKSPACE)


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
    return labels.apply_refinement(_REPO, issue_number, outcome, type_label)


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
    return labels.apply_estimation(
        _REPO, issue_number, outcome, blast_radius, touch, human_involvement, review_overhead
    )


if __name__ == "__main__":
    mcp.run()
