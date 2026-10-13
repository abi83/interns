"""The PR-loop label lifecycle as one pure decision: which `pr:*` label, issue
status, comment and coder dispatch follow from an event.

Steps gather facts, fire an event and hand the Outcome to
`lifecycle_apply.apply`; no step decides label moves itself. The issue keeps
`status:in-progress` for the whole coder-reviewer loop -- only the `pr:*` label
shows which agent is on the PR.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

from . import labels


class Event(StrEnum):
    CODER_HANDOFF = "CODER_HANDOFF"
    CODER_NO_PR = "CODER_NO_PR"
    CODER_GAVE_UP = "CODER_GAVE_UP"
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    NO_VERDICT = "NO_VERDICT"
    RED_CHECKS = "RED_CHECKS"
    REVIEW_CAP_REACHED = "REVIEW_CAP_REACHED"
    JOB_CRASHED = "JOB_CRASHED"
    JOB_CRASHED_FIX_ROUND = "JOB_CRASHED_FIX_ROUND"
    PR_CLOSED_MERGED = "PR_CLOSED_MERGED"
    PR_CLOSED_UNMERGED = "PR_CLOSED_UNMERGED"


class IssueChange(StrEnum):
    UNCHANGED = "unchanged"
    NEEDS_ATTENTION = "needs-attention"
    RETIRE_IN_PROGRESS = "retire-in-progress"


class Target(StrEnum):
    PR = "PR"
    ISSUE = "issue"


class CommentKind(StrEnum):
    CODER_NO_PR = "CODER_NO_PR"
    CODER_GAVE_UP = "CODER_GAVE_UP"
    APPROVED = "APPROVED"
    FIX_LOOP_EXHAUSTED = "FIX_LOOP_EXHAUSTED"
    CHANGES_REQUESTED_NO_ISSUE = "CHANGES_REQUESTED_NO_ISSUE"
    NO_VERDICT = "NO_VERDICT"
    RED_CHECKS = "RED_CHECKS"
    REVIEW_CAP_REACHED = "REVIEW_CAP_REACHED"
    JOB_FAILED = "JOB_FAILED"
    FIX_ROUND_FAILED = "FIX_ROUND_FAILED"
    PR_CLOSED_UNMERGED = "PR_CLOSED_UNMERGED"


class Comment(NamedTuple):
    kind: CommentKind
    target: Target


class Facts(NamedTuple):
    has_issue: bool
    has_pr: bool
    fix_rounds: int = 0
    max_fix_rounds: int = 0


class Outcome(NamedTuple):
    """`pr_label` is the sole `pr:*` label to leave on the PR, None clearing
    them all; it is not applied when there is no PR."""

    pr_label: str | None
    issue: IssueChange
    comment: Comment | None
    dispatch_fix_round: bool


def _issue_attention(facts: Facts) -> IssueChange:
    return IssueChange.NEEDS_ATTENTION if facts.has_issue else IssueChange.UNCHANGED


def _require_issue(event: Event, facts: Facts) -> None:
    if not facts.has_issue:
        raise ValueError(f"{event} requires an issue")


def _require_pr(event: Event, facts: Facts) -> None:
    if not facts.has_pr:
        raise ValueError(f"{event} requires a PR")


def _changes_requested(facts: Facts) -> Outcome:
    if facts.fix_rounds > facts.max_fix_rounds:
        return Outcome(
            labels.PR_NEEDS_ATTENTION, _issue_attention(facts), Comment(CommentKind.FIX_LOOP_EXHAUSTED, Target.PR), False
        )
    if not facts.has_issue:
        return Outcome(None, IssueChange.UNCHANGED, Comment(CommentKind.CHANGES_REQUESTED_NO_ISSUE, Target.PR), False)
    return Outcome(labels.PR_CODING, IssueChange.UNCHANGED, None, True)


def _job_crashed(facts: Facts) -> Outcome:
    if not (facts.has_issue or facts.has_pr):
        raise ValueError(f"{Event.JOB_CRASHED} requires an issue or a PR")
    target = Target.PR if facts.has_pr else Target.ISSUE
    return Outcome(labels.PR_NEEDS_ATTENTION, _issue_attention(facts), Comment(CommentKind.JOB_FAILED, target), False)


def decide(event: Event, facts: Facts) -> Outcome:
    match event:
        case Event.CODER_HANDOFF:
            _require_pr(event, facts)
            return Outcome(labels.PR_IN_REVIEW, IssueChange.UNCHANGED, None, False)
        case Event.CODER_NO_PR:
            _require_issue(event, facts)
            return Outcome(None, IssueChange.NEEDS_ATTENTION, Comment(CommentKind.CODER_NO_PR, Target.ISSUE), False)
        case Event.CODER_GAVE_UP:
            _require_issue(event, facts)
            return Outcome(None, IssueChange.NEEDS_ATTENTION, Comment(CommentKind.CODER_GAVE_UP, Target.ISSUE), False)
        case Event.APPROVED:
            _require_pr(event, facts)
            comment = Comment(CommentKind.APPROVED, Target.ISSUE) if facts.has_issue else None
            return Outcome(None, IssueChange.UNCHANGED, comment, False)
        case Event.CHANGES_REQUESTED:
            _require_pr(event, facts)
            return _changes_requested(facts)
        case Event.NO_VERDICT:
            _require_pr(event, facts)
            return Outcome(
                labels.PR_NEEDS_ATTENTION, _issue_attention(facts), Comment(CommentKind.NO_VERDICT, Target.PR), False
            )
        case Event.RED_CHECKS:
            _require_pr(event, facts)
            return Outcome(
                labels.PR_NEEDS_ATTENTION, IssueChange.UNCHANGED, Comment(CommentKind.RED_CHECKS, Target.PR), False
            )
        case Event.REVIEW_CAP_REACHED:
            _require_pr(event, facts)
            return Outcome(
                labels.PR_NEEDS_ATTENTION, IssueChange.UNCHANGED, Comment(CommentKind.REVIEW_CAP_REACHED, Target.PR), False
            )
        case Event.JOB_CRASHED:
            return _job_crashed(facts)
        case Event.JOB_CRASHED_FIX_ROUND:
            return Outcome(None, _issue_attention(facts), Comment(CommentKind.FIX_ROUND_FAILED, Target.ISSUE), False)
        case Event.PR_CLOSED_MERGED:
            change = IssueChange.RETIRE_IN_PROGRESS if facts.has_issue else IssueChange.UNCHANGED
            return Outcome(None, change, None, False)
        case Event.PR_CLOSED_UNMERGED:
            comment = Comment(CommentKind.PR_CLOSED_UNMERGED, Target.ISSUE) if facts.has_issue else None
            return Outcome(None, _issue_attention(facts), comment, False)


class Scenario(NamedTuple):
    name: str
    event: Event
    facts: Facts


_WITH_ISSUE = Facts(has_issue=True, has_pr=True)
_NO_ISSUE = Facts(has_issue=False, has_pr=True)
_NO_PR = Facts(has_issue=True, has_pr=False)

SCENARIOS = (
    Scenario("coder left a PR", Event.CODER_HANDOFF, _WITH_ISSUE),
    Scenario("coder left no PR", Event.CODER_NO_PR, _NO_PR),
    Scenario("coder fix round declined the task", Event.CODER_GAVE_UP, _WITH_ISSUE),
    Scenario("reviewer approved", Event.APPROVED, _WITH_ISSUE),
    Scenario("reviewer approved, no linked issue", Event.APPROVED, _NO_ISSUE),
    Scenario("changes requested, fix round available", Event.CHANGES_REQUESTED, Facts(True, True, 1, 1)),
    Scenario("changes requested, no linked issue", Event.CHANGES_REQUESTED, Facts(False, True, 1, 1)),
    Scenario("changes requested again, fix loop exhausted", Event.CHANGES_REQUESTED, Facts(True, True, 2, 1)),
    Scenario("changes requested again, no linked issue", Event.CHANGES_REQUESTED, Facts(False, True, 2, 1)),
    Scenario("review finished without a verdict", Event.NO_VERDICT, _WITH_ISSUE),
    Scenario("red PR checks", Event.RED_CHECKS, _WITH_ISSUE),
    Scenario("automatic review limit reached", Event.REVIEW_CAP_REACHED, _WITH_ISSUE),
    Scenario("agent job crashed on a PR", Event.JOB_CRASHED, _WITH_ISSUE),
    Scenario("agent job crashed, no PR yet", Event.JOB_CRASHED, _NO_PR),
    Scenario("coder fix round crashed", Event.JOB_CRASHED_FIX_ROUND, _WITH_ISSUE),
    Scenario("PR merged", Event.PR_CLOSED_MERGED, _WITH_ISSUE),
    Scenario("PR closed without merging", Event.PR_CLOSED_UNMERGED, _WITH_ISSUE),
)
