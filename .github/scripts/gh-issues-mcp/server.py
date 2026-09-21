"""GitHub issues MCP server for the interns pipeline."""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from pipeline import gh, prompt
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

# Lifecycle label constants -- a typo here is a NameError, not a silent orphan label.
STATUS_NEEDS_REFINEMENT = "status:needs-refinement"
STATUS_REFINED = "status:refined"
STATUS_NEEDS_ATTENTION = "status:needs-attention"
STATUS_ESTIMATED = "status:estimated"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InvalidInputError(ValueError):
    """Caller-supplied arguments are malformed or fail validation."""


class PushRefusedError(RuntimeError):
    """push_branch refused: protected branch, nothing to push, or a protected path."""


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class Comment(BaseModel):
    author: str
    created_at: str
    body: str


class RelatedIssue(BaseModel):
    number: int
    title: str
    state: str


class Issue(BaseModel):
    number: int
    title: str
    body: str
    state: str
    labels: list[str]
    comments: list[Comment]
    parent: RelatedIssue | None = None
    sub_issues: list[RelatedIssue] = []
    blocked_by: list[RelatedIssue] = []
    blocking: list[RelatedIssue] = []


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

_VIEW_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      number
      title
      body
      state
      labels(first: 20) { nodes { name } }
      comments(first: 50) {
        nodes { author { login } createdAt body }
      }
      parent          { number title state }
      subIssues(first: 20) { nodes { number title state } }
      blockedBy(first: 20) { nodes { number title state } }
      blocking(first: 20)  { nodes { number title state } }
    }
  }
}
"""


def _fetch_issue(number: int) -> Issue:
    """Run the GraphQL query and parse the response into an Issue model."""
    owner, repo = _REPO.split("/", 1)
    raw = gh.graphql(_VIEW_QUERY, owner=owner, repo=repo, number=number)["data"]["repository"]["issue"]
    return Issue(
        number=raw["number"],
        title=raw["title"],
        body=raw["body"] or "",
        state=raw["state"],
        labels=[n["name"] for n in raw["labels"]["nodes"]],
        comments=[
            Comment(
                author=c["author"]["login"],
                created_at=c["createdAt"],
                body=c["body"],
            )
            for c in raw["comments"]["nodes"]
        ],
        parent=RelatedIssue(**raw["parent"]) if raw.get("parent") else None,
        sub_issues=[RelatedIssue(**n) for n in raw["subIssues"]["nodes"]],
        blocked_by=[RelatedIssue(**n) for n in raw["blockedBy"]["nodes"]],
        blocking=[RelatedIssue(**n) for n in raw["blocking"]["nodes"]],
    )


def _write_github_output(issue: Issue) -> None:
    """Write issue fields to $GITHUB_OUTPUT for use in workflow steps."""
    output_path = os.environ.get("GITHUB_OUTPUT", "")

    def write(key: str, value: str, multiline: bool = False) -> None:
        if not output_path:
            print(f"{key}={value!r}")
            return
        with open(output_path, "ab") as f:
            if multiline:
                f.write(prompt.github_output_block(key, value.encode()))
            else:
                f.write(f"{key}={value}\n".encode())

    write("number", str(issue.number))
    write("title", issue.title)
    write("labels", ", ".join(issue.labels))
    write("body", issue.body, multiline=True)

    human_comments = [c for c in issue.comments if c.author != "github-actions"]
    if human_comments:
        parts = [
            f"### Comment by {c.author} ({c.created_at})\n{c.body}"
            for c in human_comments
        ]
        comments_text = (
            "COMMENTS (from the owner, chronological, excluding this pipeline's own"
            " comments — treat these as clarifications or amendments to the issue above):\n"
            + "\n\n---\n\n".join(parts)
        )
        write("comments", comments_text, multiline=True)
    else:
        write("comments", "", multiline=True)


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
    return _fetch_issue(issue_number).model_dump_json()


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

    output = gh.issue_edit(_REPO, issue_number, add_labels=add_labels, remove_labels=remove_labels)
    parts = []
    if add_labels:
        parts.append(f"Added: {', '.join(add_labels)}")
    if remove_labels:
        parts.append(f"Removed: {', '.join(remove_labels)}")
    return output or "\n".join(parts)


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

# Keyed by (#High, #Mid) across the four scores: size grows with either
# count, and 3+ highs is always XL.
_ROLL_UP_TABLE: dict[tuple[int, int], str] = {
    (0, 0): "XS", (0, 1): "S",  (0, 2): "S",  (0, 3): "M",  (0, 4): "M",
    (1, 0): "M",  (1, 1): "M",  (1, 2): "M",  (1, 3): "L",
    (2, 0): "L",  (2, 1): "L",  (2, 2): "L",
    (3, 0): "XL", (3, 1): "XL",
    (4, 0): "XL",
}


def _roll_up_size(blast: str, touch: str, human: str, review: str) -> str:
    """Map four Low|Mid|High scores to XS|S|M|L|XL via the (#High, #Mid) key."""
    highs = mids = 0
    for score in (blast, touch, human, review):
        s = score.strip().lower()
        if s == "high":
            highs += 1
        elif s == "mid":
            mids += 1
        elif s == "low":
            pass
        else:
            raise InvalidInputError(f"Not a Low|Mid|High score: {score!r}")
    return _ROLL_UP_TABLE[(highs, mids)]


@mcp.tool()
def apply_refinement_outcome(
    issue_number: Annotated[int, Field(description="Issue number.")],
    outcome: Annotated[Literal["refined", "needs-attention"], Field(description="Refinement outcome.")],
    type_label: Annotated[
        Literal["type:coding-task", "type:bug", "type:spike"] | None,
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
        add = [STATUS_REFINED, type_label]
        remove = [STATUS_NEEDS_REFINEMENT, STATUS_NEEDS_ATTENTION]
    elif outcome == "needs-attention":
        add, remove = [STATUS_NEEDS_ATTENTION], [STATUS_NEEDS_REFINEMENT]
    else:
        raise InvalidInputError("outcome must be 'refined' or 'needs-attention'")

    gh.issue_edit(_REPO, issue_number, add_labels=add, remove_labels=remove)
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
        size = _roll_up_size(blast_radius, touch, human_involvement, review_overhead)  # type: ignore[arg-type]
        add = [STATUS_ESTIMATED, f"size:{size}"]
        remove = [STATUS_REFINED, STATUS_NEEDS_ATTENTION]
    elif outcome == "needs-attention":
        add, remove = [STATUS_NEEDS_ATTENTION], [STATUS_REFINED]
        size = ""
    else:
        raise InvalidInputError("outcome must be 'estimated' or 'needs-attention'")

    gh.issue_edit(_REPO, issue_number, add_labels=add, remove_labels=remove)

    if outcome == "estimated":
        return f"Estimation outcome 'estimated' applied to issue #{issue_number} (size:{size})"
    return f"Estimation outcome 'needs-attention' applied to issue #{issue_number}"


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "--fetch":
        issue = _fetch_issue(int(sys.argv[2]))
        _write_github_output(issue)
    else:
        mcp.run()
