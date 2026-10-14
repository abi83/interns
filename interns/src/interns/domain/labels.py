"""Issue/PR pipeline label state machine.

Every label edit is strict: a failed `gh` call raises, so a stalled issue is
never hidden.

Each transition reads current labels first and only issues `--add-label` /
`--remove-label` for labels that actually need to change, so removing an
absent label -- which `gh` would reject -- never happens in the first place.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import NamedTuple

from .. import gh
from .size import Estimation

STATUS_NEEDS_REFINEMENT = "status:needs-refinement"
STATUS_REFINED = "status:refined"
STATUS_ESTIMATED = "status:estimated"
STATUS_IN_PROGRESS = "status:in-progress"
STATUS_NEEDS_ATTENTION = "status:needs-attention"
STATUS_READY = "status:ready"

PR_CODING = "pr:coding"
PR_IN_REVIEW = "pr:in-review"
PR_NEEDS_ATTENTION = "pr:needs-attention"



class TypeLabel(StrEnum):
    CODING_TASK = "type:coding-task"
    BUG = "type:bug"
    SPIKE = "type:spike"


TYPE_LABELS = tuple(TypeLabel)
TYPE_CODING_TASK, TYPE_BUG, TYPE_SPIKE = TYPE_LABELS


class RefinementOutcome(StrEnum):
    REFINED = "refined"
    NEEDS_ATTENTION = "needs-attention"


class EstimationOutcome(StrEnum):
    ESTIMATED = "estimated"
    NEEDS_ATTENTION = "needs-attention"

SIZE_PREFIX = "size:"

# Mutually exclusive: an issue carries at most one of these.
ISSUE_STATUS_LABELS = (STATUS_IN_PROGRESS, STATUS_NEEDS_ATTENTION, STATUS_READY)
PR_PIPELINE_LABELS = (PR_CODING, PR_IN_REVIEW, PR_NEEDS_ATTENTION)


def size_label(size: str) -> str:
    return f"{SIZE_PREFIX}{size}"


def find_size_label(current: Sequence[str]) -> str | None:
    return next((label for label in current if label.startswith(SIZE_PREFIX)), None)


class Transition(NamedTuple):
    add: list[str]
    remove: list[str]


def refined(type_label: TypeLabel) -> Transition:
    """Refinement done: hands the issue to the estimate job via its type label."""
    return Transition(
        add=[STATUS_REFINED, type_label],
        remove=[STATUS_NEEDS_REFINEMENT, STATUS_NEEDS_ATTENTION],
    )


def refinement_needs_attention() -> Transition:
    return Transition(add=[STATUS_NEEDS_ATTENTION], remove=[STATUS_NEEDS_REFINEMENT])


def estimated(size: str) -> Transition:
    return Transition(
        add=[STATUS_ESTIMATED, size_label(size)],
        remove=[STATUS_REFINED, STATUS_NEEDS_ATTENTION],
    )


def estimation_needs_attention() -> Transition:
    return Transition(add=[STATUS_NEEDS_ATTENTION], remove=[STATUS_REFINED])


def issue_labels(repo: str, issue: int) -> list[str]:
    return [label["name"] for label in gh.issue_view(repo, issue, ["labels"])["labels"]]


def pr_labels(repo: str, pr: int) -> list[str]:
    return [label["name"] for label in gh.pr_view(repo, pr, ["labels"])["labels"]]


def _changed_labels(current: Sequence[str], add: Sequence[str], remove: Sequence[str]) -> tuple[list[str], list[str]]:
    have = set(current)
    return [label for label in add if label not in have], [label for label in remove if label in have]


def edit_issue_labels(repo: str, issue: int, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None:
    """Add/remove specific issue labels, skipping any already in the wanted
    state -- in particular a `remove` that isn't present, which `gh` would
    otherwise reject. `gh` failures propagate."""
    add_labels, remove_labels = _changed_labels(issue_labels(repo, issue), add, remove)
    if add_labels or remove_labels:
        gh.issue_edit(repo, issue, add_labels=add_labels, remove_labels=remove_labels)


def edit_pr_labels(repo: str, pr: int, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None:
    """PR counterpart of `edit_issue_labels`."""
    add_labels, remove_labels = _changed_labels(pr_labels(repo, pr), add, remove)
    if add_labels or remove_labels:
        gh.pr_edit(repo, pr, add_labels=add_labels, remove_labels=remove_labels)


def apply_transition(repo: str, issue: int, transition: Transition) -> None:
    """A failed edit raises, so the calling agent learns the lifecycle didn't
    advance."""
    edit_issue_labels(repo, issue, add=transition.add, remove=transition.remove)


def set_issue_status(repo: str, issue: int, target: str) -> None:
    """Move an issue to one lifecycle status, removing whichever of the
    others it currently carries. The issue-pipeline's own labels
    (needs-refinement, refined, estimated) are left untouched."""
    remove = [label for label in ISSUE_STATUS_LABELS if label != target]
    edit_issue_labels(repo, issue, add=[target], remove=remove)


def set_pr_pipeline_label(repo: str, pr: int, target: str | None = None) -> None:
    """Set the PR's pipeline label (which agent is on it now, or
    pr:needs-attention once escalated), or clear all of them when `target` is
    None. Mutually exclusive: only the target survives, so a coder/reviewer
    pickup or a clear drops a stale pr:needs-attention. Only touches labels
    that change."""
    add = [target] if target else []
    remove = [label for label in PR_PIPELINE_LABELS if label != target]
    edit_pr_labels(repo, pr, add=add, remove=remove)


def escalate_pr(repo: str, pr: int) -> None:
    """Mark a PR as stuck: the pipeline escalated it to a human and no agent
    is working it. Cleared by the next pickup or an APPROVE."""
    set_pr_pipeline_label(repo, pr, PR_NEEDS_ATTENTION)


def set_issue_type(repo: str, issue: int, type_label: TypeLabel) -> str:
    """Make `type_label` the issue's only `type:*` label.

    The only label write an agent gets besides the outcome tools: it can
    never touch status:*, pr:* or size:*.
    """
    edit_issue_labels(repo, issue, add=[type_label], remove=[t for t in TYPE_LABELS if t != type_label])
    return f"Issue #{issue} type set to {type_label}"


def apply_refinement(
    repo: str,
    issue: int,
    outcome: RefinementOutcome,
    type_label: TypeLabel | None = None,
) -> str:
    """Apply the lifecycle label transition after refinement.

    refined        → requires type_label; transitions issue to status:refined.
    needs-attention → transitions issue to status:needs-attention.
    Raises gh.InvalidInputError when refined comes without a type_label.
    """
    match outcome:
        case RefinementOutcome.REFINED:
            if type_label is None:
                raise gh.InvalidInputError("type_label is required when outcome='refined'")
            transition = refined(type_label)
        case RefinementOutcome.NEEDS_ATTENTION:
            transition = refinement_needs_attention()
    apply_transition(repo, issue, transition)
    return f"Refinement outcome '{outcome}' applied to issue #{issue}"


def apply_estimation(repo: str, issue: int, outcome: EstimationOutcome, estimation: Estimation | None = None) -> str:
    """Apply the lifecycle label transition after estimation.

    estimated      → rolls the four scores into a size:* label, then posts the
                     score comment. The transition goes first and is strict, so
                     a failed transition leaves no comment behind.
    needs-attention → transitions issue to status:needs-attention.
    Raises gh.InvalidInputError when estimated comes without scores; ValueError for bad scores.
    """
    match outcome:
        case EstimationOutcome.ESTIMATED:
            if estimation is None:
                raise gh.InvalidInputError(
                    "blast_radius, touch, human_involvement, and review_overhead are all required when outcome='estimated'"
                )
            size = estimation.size()
            apply_transition(repo, issue, estimated(size))
            gh.issue_comment(repo, issue, estimation.comment())
            return f"Estimation outcome 'estimated' applied to issue #{issue} ({size_label(size)})"
        case EstimationOutcome.NEEDS_ATTENTION:
            apply_transition(repo, issue, estimation_needs_attention())
            return f"Estimation outcome 'needs-attention' applied to issue #{issue}"
