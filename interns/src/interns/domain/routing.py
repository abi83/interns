"""Event -> pipeline job routing: the entry edge of the pipeline state machine.

`parse_event` turns the raw GitHub event payload into a `GithubEvent`, raising
on any shape the caller templates don't subscribe to. `route` is a pure
function from that event to the single job it starts (or `Job.NONE` with the
reason), so every trigger decision lives here instead of in workflow `if:`
conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..config import ReviewerTrigger
from . import labels


class Job(StrEnum):
    REFINE = "refine"
    ESTIMATE = "estimate"
    CODER = "coder"
    REVIEWER = "reviewer"
    PR_CLOSED = "pr_closed"
    NONE = "none"


@dataclass(frozen=True)
class IssueLabeled:
    issue: int
    label: str


@dataclass(frozen=True)
class PullRequestEvent:
    action: str
    number: int
    draft: bool
    fork: bool
    author_login: str
    author_type: str


@dataclass(frozen=True)
class RunPullRequest:
    number: int
    head_sha: str


@dataclass(frozen=True)
class WorkflowRunEvent:
    """A workflow of the consumer repo finished; `own` when it is the pipeline's own workflow."""

    head_sha: str
    own: bool
    pull_request: RunPullRequest | None


@dataclass(frozen=True)
class Dispatch:
    phase: str
    issue: int | None
    pr: int | None
    fix_round: bool


GithubEvent = IssueLabeled | PullRequestEvent | WorkflowRunEvent | Dispatch


@dataclass(frozen=True)
class RouteConfig:
    """What the calling workflow runs; a routed job it doesn't own is skipped."""

    handles: frozenset[Job]
    trigger: ReviewerTrigger

    @classmethod
    def parse(cls, handles: str, trigger: ReviewerTrigger) -> RouteConfig:
        return cls(handles=frozenset(Job(name) for name in handles.split(",")), trigger=trigger)


@dataclass(frozen=True)
class Route:
    job: Job
    issue: int | None = None
    pr: int | None = None
    fix_round: bool = False
    skip_reason: str = ""


SUPPORTED_ACTIONS: dict[str, frozenset[str]] = {
    "issues": frozenset({"labeled"}),
    "pull_request": frozenset({"opened", "ready_for_review", "synchronize", "closed"}),
    "workflow_run": frozenset({"completed"}),
    "workflow_dispatch": frozenset(),
}

LABEL_JOBS: dict[str, Job] = {
    labels.STATUS_NEEDS_REFINEMENT: Job.REFINE,
    labels.STATUS_REFINED: Job.ESTIMATE,
    labels.STATUS_READY: Job.CODER,
}

ISSUE_PHASES: dict[str, Job] = {"refine": Job.REFINE, "estimate": Job.ESTIMATE, "coder": Job.CODER}
PR_PHASES: dict[str, Job] = {"reviewer": Job.REVIEWER}


def _check_action(name: str, payload: dict) -> str:
    action = payload.get("action")
    if action not in SUPPORTED_ACTIONS[name]:
        raise ValueError(f"unsupported {name} action: {action!r}")
    return action


def pull_request_event(action: str, pr: dict) -> PullRequestEvent:
    """From a pull request object, as in a `pull_request` payload or the REST API."""
    head_repo = pr["head"]["repo"]
    return PullRequestEvent(
        action=action,
        number=pr["number"],
        draft=pr["draft"],
        fork=head_repo is None or head_repo["fork"],
        author_login=pr["user"]["login"],
        author_type=pr["user"]["type"],
    )


def _parse_workflow_run(payload: dict) -> WorkflowRunEvent:
    _check_action("workflow_run", payload)
    run = payload["workflow_run"]
    pull_requests = run["pull_requests"]
    first = pull_requests[0] if pull_requests else None
    return WorkflowRunEvent(
        head_sha=run["head_sha"],
        own=run["workflow_id"] == payload["workflow"]["id"],
        pull_request=None if first is None else RunPullRequest(first["number"], first["head"]["sha"]),
    )


def _optional_int(value: str | int | None) -> int | None:
    return int(value) if value not in (None, "") else None


def _parse_dispatch(payload: dict) -> Dispatch:
    inputs = payload.get("inputs") or {}
    return Dispatch(
        phase=inputs.get("phase") or "",
        issue=_optional_int(inputs.get("issue_number")),
        pr=_optional_int(inputs.get("pr_number")),
        fix_round=str(inputs.get("fix_round")).lower() == "true",
    )


def parse_event(name: str, payload: dict) -> GithubEvent:
    if name not in SUPPORTED_ACTIONS:
        raise ValueError(f"unsupported event: {name!r}")
    if name == "workflow_dispatch":
        return _parse_dispatch(payload)
    if name == "pull_request":
        return pull_request_event(_check_action(name, payload), payload["pull_request"])
    if name == "workflow_run":
        return _parse_workflow_run(payload)
    _check_action(name, payload)
    return IssueLabeled(issue=payload["issue"]["number"], label=payload["label"]["name"])


def _route_label(event: IssueLabeled) -> Route:
    job = LABEL_JOBS.get(event.label)
    if job is None:
        return Route(Job.NONE, skip_reason=f"label {event.label!r} starts no pipeline job")
    return Route(job, issue=event.issue)


def _unreviewed_reason(event: PullRequestEvent, trigger: ReviewerTrigger) -> str:
    if event.draft:
        return "draft PR: reviewed once marked ready"
    if event.fork:
        return "fork PR: no access to secrets"
    is_bot = event.author_type == "Bot"
    if is_bot and not trigger.coder_prs:
        return "bot-authored PR and agents.reviewer.trigger.coder_prs is false"
    if not is_bot and not trigger.human_prs:
        return "human-authored PR and agents.reviewer.trigger.human_prs is false"
    if event.action == "synchronize" and not trigger.rereview_on_push:
        return "push to an open PR and agents.reviewer.trigger.rereview_on_push is false"
    return ""


def _route_pull_request(event: PullRequestEvent, trigger: ReviewerTrigger) -> Route:
    if event.action == "closed":
        return Route(Job.PR_CLOSED, pr=event.number)
    reason = _unreviewed_reason(event, trigger)
    if reason:
        return Route(Job.NONE, pr=event.number, skip_reason=reason)
    return Route(Job.REVIEWER, pr=event.number)


def _route_workflow_run(event: WorkflowRunEvent) -> Route:
    if event.own:
        return Route(Job.NONE, skip_reason="the pipeline's own workflow finished")
    pr = event.pull_request
    if pr is None:
        return Route(Job.NONE, skip_reason="workflow run has no open same-repo PR")
    if pr.head_sha != event.head_sha:
        return Route(Job.NONE, pr=pr.number, skip_reason="workflow run is for an outdated commit")
    return Route(Job.REVIEWER, pr=pr.number)


def _required(value: int | None, name: str, phase: str) -> int:
    if value is None:
        raise ValueError(f"phase {phase!r} needs {name}")
    return value


def _route_dispatch(event: Dispatch) -> Route:
    if event.phase in PR_PHASES:
        return Route(PR_PHASES[event.phase], pr=_required(event.pr, "pr_number", event.phase))
    if event.phase in ISSUE_PHASES:
        job = ISSUE_PHASES[event.phase]
        return Route(job, issue=_required(event.issue, "issue_number", event.phase),
                     fix_round=job is Job.CODER and event.fix_round)
    raise ValueError(f"unknown dispatch phase: {event.phase!r}")


def _routed(event: GithubEvent, trigger: ReviewerTrigger) -> Route:
    match event:
        case IssueLabeled():
            return _route_label(event)
        case PullRequestEvent():
            return _route_pull_request(event, trigger)
        case WorkflowRunEvent():
            return _route_workflow_run(event)
        case Dispatch():
            return _route_dispatch(event)


def route(event: GithubEvent, config: RouteConfig) -> Route:
    routed = _routed(event, config.trigger)
    if routed.job is Job.NONE or routed.job in config.handles:
        return routed
    return Route(Job.NONE, skip_reason=f"{routed.job.value} job belongs to the other workflow")
