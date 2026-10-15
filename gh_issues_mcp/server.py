"""GitHub issues MCP server for the interns pipeline."""

from __future__ import annotations

import dataclasses
import functools
import inspect
import json
import os
import pathlib
from collections.abc import Callable
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from interns import cli, gh
from interns.domain import issues, labels, push
from interns.domain.size import Estimation
from interns.gh import GhCommandError, InvalidInputError, PushRefusedError
from pydantic import BaseModel, Field

__all__ = ["GhCommandError", "InvalidInputError", "PushRefusedError", "build_server"]

TOOLS_ENV = "INTERNS_MCP_TOOLS"
_JOB_LOG_LIMIT = 30_000

_TOOLS: dict[str, Callable[..., str]] = {}


def _tool(fn: Callable[..., str]) -> Callable[..., str]:
    _TOOLS[fn.__name__] = fn
    return fn


_ANTICIPATED_ERRORS = (InvalidInputError, GhCommandError, PushRefusedError)


def _surface_anticipated_errors(fn: Callable[..., str]) -> Callable[..., str]:
    """The SDK shows the model only `ToolError` messages; any other exception reaches it as a bare crash."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> str:
        try:
            return fn(*args, **kwargs)
        except _ANTICIPATED_ERRORS as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def _repo() -> str:
    return cli.require_env("GITHUB_REPOSITORY")


def _workspace() -> str:
    return cli.require_env("GITHUB_WORKSPACE")


def _describe_labels(fn: Callable[..., str]) -> Callable[..., str]:
    """Advertise the manifest's label names on `list_issues`; read at server build, not at import."""
    description = f"Label to filter by. Pass '' (or omit) to list all open issues. Valid labels: {', '.join(_load_label_names())}."

    @functools.wraps(fn)
    def wrapper(*args, **kwargs) -> str:
        return fn(*args, **kwargs)

    signature = inspect.signature(fn, eval_str=True)
    label = signature.parameters["label"].replace(annotation=Annotated[str, Field(description=description)])
    wrapper.__signature__ = signature.replace(parameters=[label])  # type: ignore[attr-defined]
    return wrapper


def build_server(tool_names: list[str]) -> MCPServer:
    """An MCP server exposing exactly `tool_names`; unknown or empty fails fast."""
    if not tool_names:
        raise ValueError(f"{TOOLS_ENV} must name at least one tool")
    unknown = sorted(set(tool_names) - _TOOLS.keys())
    if unknown:
        raise ValueError(f"Unknown tool(s) in {TOOLS_ENV}: {', '.join(unknown)}. Known: {', '.join(sorted(_TOOLS))}")
    _repo()
    _workspace()
    server = MCPServer("gh-issues")
    for name in tool_names:
        fn = _surface_anticipated_errors(_TOOLS[name])
        server.add_tool(_describe_labels(fn) if name == "list_issues" else fn)
    return server

_LABELS_JSON = pathlib.Path(__file__).parent.parent / ".github" / "labels.json"


class InlineComment(BaseModel):
    path: str = Field(description="File path relative to repo root.")
    line: int = Field(description="Line number in the file.", ge=1)
    body: str = Field(description="Comment text.", min_length=1, max_length=10000)


def _load_label_names() -> list[str]:
    data = json.loads(_LABELS_JSON.read_text())
    return [entry["name"] for entry in data["labels"]]


@_tool
def list_issues(
    label: Annotated[str, Field(description="Label to filter by. Pass '' (or omit) to list all open issues.")] = "",
) -> str:
    """List open issues in the repository.

    Returns a JSON array; each element has number, title, labels, state.
    """
    return json.dumps(gh.issue_list(_repo(), label=label))


@_tool
def view_issue(
    issue_number: Annotated[int, Field(description="Issue number to fetch.")],
) -> str:
    """Get full details of one issue: number, title, body, labels, state, comments,
    and GitHub relationships (parent, sub-issues, blockedBy, blocking).

    Returns a flat JSON object — labels is a list of strings, comments is a list
    of {author, created_at, body} objects.
    """
    return json.dumps(dataclasses.asdict(issues.fetch_issue(_repo(), issue_number)))


@_tool
def comment_issue(
    issue_number: Annotated[int, Field(description="Issue number to comment on.")],
    body: Annotated[str, Field(description="Comment body (markdown).", min_length=1, max_length=10000)],
) -> str:
    """Post a comment on an issue."""
    return gh.issue_comment(_repo(), issue_number, body) or f"Comment posted on issue #{issue_number}"


@_tool
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
    return gh.issue_edit_validated(_repo(), issue_number, body=body, title=title)


@_tool
def set_issue_type(
    issue_number: Annotated[int, Field(description="Issue number.")],
    type_label: Annotated[labels.TypeLabel, Field(description="The issue's type label.")],
) -> str:
    """Make type_label the issue's only type:* label, removing any other type:* label.

    Touches no other labels; lifecycle labels change only through the outcome tools.
    """
    return labels.set_issue_type(_repo(), issue_number, type_label)


@_tool
def view_pr(
    pr_number: Annotated[int, Field(description="PR number to fetch.")],
) -> str:
    """Get a pull request's title, description (body) and conversation comments.

    Returns a JSON object with title, body and comments.
    """
    return json.dumps(gh.pr_view(_repo(), pr_number, ["title", "body", "comments"]))


@_tool
def view_pr_diff(
    pr_number: Annotated[int, Field(description="PR number whose diff to fetch.")],
) -> str:
    """Get the PR's full unified diff as GitHub computes it, covering every changed path
    (including files a working-tree diff may not show, such as .github/workflows/**).
    """
    return gh.pr_diff(_repo(), pr_number)


@_tool
def pr_checks(
    pr_number: Annotated[int, Field(description="PR number whose checks to list.")],
) -> str:
    """List the PR's checks.

    Returns a JSON array of {name, bucket, link}; empty when none are reported yet.
    The job ID for `view_job_log` is the number after `/job/` in link.
    """
    return json.dumps(gh.pr_checks(_repo(), pr_number))


@_tool
def view_job_log(
    job_id: Annotated[int, Field(description="Job ID, from a check's link.")],
) -> str:
    """Get the log of one CI job, to judge its real output rather than just pass/fail.

    Long logs are cut to their last characters, where failures and plan output usually sit.
    """
    log = gh.job_log(_repo(), job_id)
    if len(log) <= _JOB_LOG_LIMIT:
        return log
    return f"[log truncated to its last {_JOB_LOG_LIMIT} characters]\n{log[-_JOB_LOG_LIMIT:]}"


@_tool
def comment_pr(
    pr_number: Annotated[int, Field(description="PR number to comment on.")],
    body: Annotated[str, Field(description="Comment body (markdown).", min_length=1, max_length=10000)],
) -> str:
    """Post a comment on a pull request."""
    return gh.pr_comment(_repo(), pr_number, body) or f"Comment posted on PR #{pr_number}"


@_tool
def open_pr(
    issue_number: Annotated[int, Field(description="Issue number this PR closes.")],
    title: Annotated[str, Field(description="PR title (single line, Conventional Commit format).", min_length=5, max_length=300)],
    body: Annotated[str, Field(description="PR body (markdown). 'Closes #N' is appended automatically.", min_length=10, max_length=10000)],
) -> str:
    """Open a PR from the current branch.

    Appends 'Closes #<issue_number>' to the body automatically so the PR is
    linked to the issue via GitHub's closing-reference mechanism.
    """
    return push.pr_open_for_issue(_repo(), _workspace(), issue_number, title, body)


@_tool
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
    return json.dumps(gh.pr_submit_review(_repo(), pr_number, event, body, comment_dicts))


@_tool
def push_branch() -> str:
    """Squash the current branch to one commit and push it to origin.

    Refuses to push main/master, branches with no commits beyond origin's default branch,
    or commits that touch protected paths (.github/workflows/ or .github/scripts/).
    Squashing happens before the protected-path check so an intermediate-only
    edit to a protected path is collapsed and doesn't trigger a false positive.
    """
    return push.push_branch(_repo(), _workspace())


# Outcome tools apply lifecycle label transitions directly, so the refiner/estimator need no Write access.
@_tool
def apply_refinement_outcome(
    issue_number: Annotated[int, Field(description="Issue number.")],
    outcome: Annotated[labels.RefinementOutcome, Field(description="Refinement outcome.")],
    type_label: Annotated[
        labels.TypeLabel | None,
        Field(description="Required when outcome='refined'. The type label for this issue."),
    ] = None,
) -> str:
    """Apply the lifecycle label transition after refinement.

    refined       → requires type_label; removes status:needs-refinement and
                    status:needs-attention, adds status:refined and the type label
                    (which triggers the estimate job).
    needs-attention → removes status:needs-refinement, adds status:needs-attention.
    """
    return labels.apply_refinement(_repo(), issue_number, outcome, type_label)


@_tool
def apply_estimation_outcome(
    issue_number: Annotated[int, Field(description="Issue number.")],
    outcome: Annotated[labels.EstimationOutcome, Field(description="Estimation outcome.")],
    estimation: Annotated[
        Estimation | None,
        Field(
            description=(
                "Required when outcome='estimated'. Four scores (blast_radius: risk of breaking existing "
                "functionality; touch: number of files/components touched; human_involvement: expected "
                "back-and-forth with the owner; review_overhead: reviewer effort), each with a level "
                "(Low|Mid|High) and a one-sentence reason."
            )
        ),
    ] = None,
) -> str:
    """Submit the final estimation result.

    Call on the normal path after scoring: advances the issue to
    status:estimated with a computed size label, then posts the four-line
    score comment. Call with outcome='needs-attention' when the issue cannot
    be sized.
    """
    return labels.apply_estimation(_repo(), issue_number, outcome, estimation)


if __name__ == "__main__":
    build_server([n.strip() for n in os.environ[TOOLS_ENV].split(",") if n.strip()]).run()
