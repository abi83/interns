"""GitHub issues MCP server for the interns pipeline."""

import json
import os
import pathlib
import re
import subprocess
from typing import Annotated, Optional

from mcp.server.mcpserver import MCPServer
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
    parent: Optional[RelatedIssue] = None
    sub_issues: list[RelatedIssue] = []
    blocked_by: list[RelatedIssue] = []
    blocking: list[RelatedIssue] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_label_names() -> list[str]:
    try:
        data = json.loads(_LABELS_JSON.read_text())
        return [entry["name"] for entry in data.get("labels", [])]
    except (OSError, KeyError, json.JSONDecodeError):
        return []


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
    result = subprocess.run(
        [
            "gh", "api", "graphql",
            "-f", f"query={_VIEW_QUERY}",
            "-F", f"owner={owner}",
            "-F", f"repo={repo}",
            "-F", f"number={number}",
        ],
        capture_output=True, text=True, check=True,
    )
    raw = json.loads(result.stdout)["data"]["repository"]["issue"]
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
        with open(output_path, "a") as f:
            if multiline:
                sentinel = f"EOF_{key.upper()}"
                f.write(f"{key}<<{sentinel}\n{value}\n{sentinel}\n")
            else:
                f.write(f"{key}={value}\n")

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
    cmd = [
        "gh", "issue", "list",
        "--repo", _REPO,
        "--state", "open",
        "--json", "number,title,labels,state",
        "--limit", "100",
    ]
    if label:
        cmd += ["--label", label]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


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
    body: Annotated[str, Field(description="Comment body (markdown).")],
) -> str:
    """Post a comment on an issue."""
    result = subprocess.run(
        ["gh", "issue", "comment", str(issue_number), "--repo", _REPO, "--body", body],
        capture_output=True, text=True, check=True,
    )
    return result.stdout or f"Comment posted on issue #{issue_number}"


@mcp.tool()
def edit_issue_body(
    issue_number: Annotated[int, Field(description="Issue number.")],
    body: Annotated[str, Field(description="New issue body (markdown).")],
) -> str:
    """Set the body of an issue."""
    result = subprocess.run(
        ["gh", "issue", "edit", str(issue_number), "--repo", _REPO, "--body", body],
        capture_output=True, text=True, check=True,
    )
    return result.stdout or f"Body updated on issue #{issue_number}"


@mcp.tool()
def edit_issue_title(
    issue_number: Annotated[int, Field(description="Issue number.")],
    title: Annotated[str, Field(description="New issue title (single line).")],
) -> str:
    """Set the title of an issue."""
    if "\n" in title:
        raise ValueError("Title must be a single line")
    result = subprocess.run(
        ["gh", "issue", "edit", str(issue_number), "--repo", _REPO, "--title", title],
        capture_output=True, text=True, check=True,
    )
    return result.stdout or f"Title updated on issue #{issue_number}"


@mcp.tool()
def edit_issue_labels(
    issue_number: Annotated[int, Field(description="Issue number.")],
    add_labels: Annotated[list[str], Field(description="Labels to add.")] = [],
    remove_labels: Annotated[list[str], Field(description="Labels to remove.")] = [],
) -> str:
    """Add or remove labels on an issue.

    Only labels that exist in the repository are accepted. Pass an empty list
    to skip adding or removing.
    """
    if not add_labels and not remove_labels:
        return "Nothing to do"

    valid_result = subprocess.run(
        [
            "gh", "label", "list",
            "--repo", _REPO,
            "--limit", "500",
            "--json", "name",
            "--jq", ".[].name",
        ],
        capture_output=True, text=True, check=True,
    )
    valid = set(valid_result.stdout.splitlines())

    unknown_add = [lbl for lbl in add_labels if lbl not in valid]
    unknown_remove = [lbl for lbl in remove_labels if lbl not in valid]
    if unknown_add or unknown_remove:
        msgs = []
        if unknown_add:
            msgs.append(f"Labels don't exist, not added: {', '.join(unknown_add)}")
        if unknown_remove:
            msgs.append(f"Labels don't exist, not removed: {', '.join(unknown_remove)}")
        raise ValueError("\n".join(msgs))

    args = ["gh", "issue", "edit", str(issue_number), "--repo", _REPO]
    for lbl in add_labels:
        args += ["--add-label", lbl]
    for lbl in remove_labels:
        args += ["--remove-label", lbl]

    result = subprocess.run(args, capture_output=True, text=True, check=True)
    parts = []
    if add_labels:
        parts.append(f"Added: {', '.join(add_labels)}")
    if remove_labels:
        parts.append(f"Removed: {', '.join(remove_labels)}")
    return result.stdout or "\n".join(parts)


# ---------------------------------------------------------------------------
# PR write tools
# ---------------------------------------------------------------------------


@mcp.tool()
def comment_pr(
    pr_number: Annotated[int, Field(description="PR number to comment on.")],
    body: Annotated[str, Field(description="Comment body (markdown).")],
) -> str:
    """Post a comment on a pull request."""
    result = subprocess.run(
        ["gh", "pr", "comment", str(pr_number), "--repo", _REPO, "--body", body],
        capture_output=True, text=True, check=True,
    )
    return result.stdout or f"Comment posted on PR #{pr_number}"


@mcp.tool()
def open_pr(
    issue_number: Annotated[int, Field(description="Issue number this PR closes.")],
    title: Annotated[str, Field(description="PR title (single line, Conventional Commit format).")],
    body: Annotated[str, Field(description="PR body (markdown). 'Closes #N' is appended automatically.")],
) -> str:
    """Open a PR from the current branch.

    Appends 'Closes #<issue_number>' to the body automatically so the PR is
    linked to the issue via GitHub's closing-reference mechanism.
    """
    full_body = f"{body}\n\nCloses #{issue_number}"
    result = subprocess.run(
        ["gh", "pr", "create", "--repo", _REPO, "--title", title, "--body", full_body],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


@mcp.tool()
def submit_pr_review(
    pr_number: Annotated[int, Field(description="PR number.")],
    event: Annotated[str, Field(description="Review verdict: APPROVE or REQUEST_CHANGES.")],
    body: Annotated[str, Field(description="Review summary comment.")],
    comments: Annotated[
        list[dict],
        Field(description='Inline comments: [{"path": "...", "line": 123, "body": "..."}]. Empty for APPROVE.'),
    ] = [],
) -> str:
    """Submit a formal PR review (verdict + optional inline comments) atomically."""
    if event not in ("APPROVE", "REQUEST_CHANGES"):
        raise ValueError("event must be APPROVE or REQUEST_CHANGES")
    payload = {"event": event, "body": body, "comments": comments}
    result = subprocess.run(
        [
            "gh", "api", "--method", "POST",
            f"repos/{_REPO}/pulls/{pr_number}/reviews",
            "--input", "-",
        ],
        input=json.dumps(payload),
        capture_output=True, text=True, check=True,
    )
    return result.stdout


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
    ws = _WORKSPACE or None

    def git(*args: str) -> str:
        r = subprocess.run(
            ["git"] + list(args), cwd=ws, capture_output=True, text=True, check=True
        )
        return r.stdout.strip()

    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    if branch in ("main", "master"):
        raise ValueError(f"Refusing to push {branch} directly")

    git("fetch", "origin", "main", "--quiet")
    base = git("merge-base", "origin/main", "HEAD")
    head = git("rev-parse", "HEAD")

    if base == head:
        raise ValueError("No commits beyond origin/main — nothing to push")

    message = git("log", "-1", "--format=%B")
    git("reset", "--soft", base)
    git("commit", "--quiet", "-m", message)

    changed = git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
    protected = [p for p in changed.splitlines() if re.search(_PROTECTED_PATHS_RE, p)]
    if protected:
        paths = "\n".join(f"  {p}" for p in protected)
        raise ValueError(
            f"Cannot push: changes touch protected paths (drop these edits and push again):\n{paths}"
        )

    git("push", "--force-with-lease", "-u", "origin", branch)
    return f"Branch {branch!r} squashed and pushed to origin"


# ---------------------------------------------------------------------------
# Outcome tools — apply pipeline lifecycle label transitions directly,
# so refiner/estimator need no Write access and no marker files on disk.
# ---------------------------------------------------------------------------

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
            raise ValueError(f"Not a Low|Mid|High score: {score!r}")
    return _ROLL_UP_TABLE[(highs, mids)]


@mcp.tool()
def apply_refinement_outcome(
    issue_number: Annotated[int, Field(description="Issue number.")],
    outcome: Annotated[str, Field(description="'refined' or 'needs-attention'.")],
) -> str:
    """Apply the lifecycle label transition after refinement.

    refined       → removes status:needs-refinement and status:needs-attention,
                    adds status:refined (which triggers the estimate job).
    needs-attention → removes status:needs-refinement, adds status:needs-attention.
    """
    if outcome == "refined":
        add, remove = ["status:refined"], ["status:needs-refinement", "status:needs-attention"]
    elif outcome == "needs-attention":
        add, remove = ["status:needs-attention"], ["status:needs-refinement"]
    else:
        raise ValueError("outcome must be 'refined' or 'needs-attention'")

    args = ["gh", "issue", "edit", str(issue_number), "--repo", _REPO]
    for lbl in add:
        args += ["--add-label", lbl]
    for lbl in remove:
        args += ["--remove-label", lbl]
    subprocess.run(args, capture_output=True, text=True, check=True)
    return f"Refinement outcome '{outcome}' applied to issue #{issue_number}"


@mcp.tool()
def apply_estimation_outcome(
    issue_number: Annotated[int, Field(description="Issue number.")],
    outcome: Annotated[str, Field(description="'estimated' or 'needs-attention'.")],
    blast_radius: Annotated[str, Field(description="Low|Mid|High. Required when outcome='estimated'.")] = "",
    touch: Annotated[str, Field(description="Low|Mid|High. Required when outcome='estimated'.")] = "",
    human_involvement: Annotated[str, Field(description="Low|Mid|High. Required when outcome='estimated'.")] = "",
    review_overhead: Annotated[str, Field(description="Low|Mid|High. Required when outcome='estimated'.")] = "",
) -> str:
    """Apply the lifecycle label transition after estimation.

    estimated     → rolls the four Low|Mid|High scores into a size:* label,
                    then removes status:refined and status:needs-attention,
                    adds status:estimated and the computed size:* label.
    needs-attention → removes status:refined, adds status:needs-attention.
    """
    if outcome == "estimated":
        size = _roll_up_size(blast_radius, touch, human_involvement, review_overhead)
        add = ["status:estimated", f"size:{size}"]
        remove = ["status:refined", "status:needs-attention"]
    elif outcome == "needs-attention":
        add, remove = ["status:needs-attention"], ["status:refined"]
        size = ""
    else:
        raise ValueError("outcome must be 'estimated' or 'needs-attention'")

    args = ["gh", "issue", "edit", str(issue_number), "--repo", _REPO]
    for lbl in add:
        args += ["--add-label", lbl]
    for lbl in remove:
        args += ["--remove-label", lbl]
    subprocess.run(args, capture_output=True, text=True, check=True)

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
