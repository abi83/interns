"""Issue/PR pipeline label state machine.

Label edits here are best-effort: a transient `gh` failure (rate limit, a
concurrent edit) shouldn't abort the calling workflow step over a label that a
later run will just re-set. Each edit call routes through `best_effort.call`
with `gh.GhCommandError` -- the repo-wide single mechanism that logs a warning
and continues rather than raising.

That's also what makes the "target label not already present" case cheap:
every transition reads current labels first and only issues `--add-label` /
`--remove-label` for labels that actually need to change, so removing an
absent label -- which `gh` would reject -- never happens in the first place.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, NamedTuple

from . import best_effort, gh

if TYPE_CHECKING:
    from .ctx import ActionsCtx
from .size import roll_up_size

STATUS_NEEDS_REFINEMENT = "status:needs-refinement"
STATUS_REFINED = "status:refined"
STATUS_ESTIMATED = "status:estimated"
STATUS_IN_PROGRESS = "status:in-progress"
STATUS_NEEDS_ATTENTION = "status:needs-attention"
STATUS_READY = "status:ready"

PR_CODING = "pr:coding"
PR_IN_REVIEW = "pr:in-review"
PR_NEEDS_ATTENTION = "pr:needs-attention"

TYPE_CODING_TASK = "type:coding-task"
TYPE_BUG = "type:bug"
TYPE_SPIKE = "type:spike"

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


def refined(type_label: str) -> Transition:
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


def edit_issue_labels_strict(repo: str, issue: int, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None:
    """Add/remove specific issue labels, skipping any already in the wanted
    state -- in particular a `remove` that isn't present, which `gh` would
    otherwise reject. `gh` failures propagate."""
    add_labels, remove_labels = _changed_labels(issue_labels(repo, issue), add, remove)
    if add_labels or remove_labels:
        gh.issue_edit(repo, issue, add_labels=add_labels, remove_labels=remove_labels)


def edit_issue_labels(repo: str, issue: int, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None:
    """Best-effort `edit_issue_labels_strict`."""
    best_effort.call("issue label edit", gh.GhCommandError, edit_issue_labels_strict, repo, issue, add, remove)


def edit_pr_labels(repo: str, pr: int, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None:
    """PR counterpart of `edit_issue_labels` (always best-effort)."""
    add_labels, remove_labels = _changed_labels(pr_labels(repo, pr), add, remove)
    if add_labels or remove_labels:
        best_effort.call("PR label edit", gh.GhCommandError, gh.pr_edit, repo, pr, add_labels=add_labels, remove_labels=remove_labels)


def apply_transition(repo: str, issue: int, transition: Transition) -> None:
    """Strict: a failed edit raises, so the calling agent learns the
    lifecycle didn't advance."""
    edit_issue_labels_strict(repo, issue, add=transition.add, remove=transition.remove)


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


def edit_issue_labels_validated(
    repo: str,
    issue: int,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> str:
    """Add or remove labels after verifying they exist in the repo.

    Raises gh.InvalidInputError for any label not present in the repo.
    Returns a human-readable summary, or 'Nothing to do' when both lists are empty.
    """
    add = add or []
    remove = remove or []
    if not add and not remove:
        return "Nothing to do"
    valid = set(gh.label_names(repo))
    unknown_add = [lbl for lbl in add if lbl not in valid]
    unknown_remove = [lbl for lbl in remove if lbl not in valid]
    if unknown_add or unknown_remove:
        msgs = []
        if unknown_add:
            msgs.append(f"Labels don't exist, not added: {', '.join(unknown_add)}")
        if unknown_remove:
            msgs.append(f"Labels don't exist, not removed: {', '.join(unknown_remove)}")
        raise gh.InvalidInputError("\n".join(msgs))
    edit_issue_labels_strict(repo, issue, add=add, remove=remove)
    parts = []
    if add:
        parts.append(f"Added: {', '.join(add)}")
    if remove:
        parts.append(f"Removed: {', '.join(remove)}")
    return "\n".join(parts)


def apply_refinement(
    repo: str,
    issue: int,
    outcome: str,
    type_label: str | None = None,
) -> str:
    """Apply the lifecycle label transition after refinement.

    refined        → requires type_label; transitions issue to status:refined.
    needs-attention → transitions issue to status:needs-attention.
    Raises gh.InvalidInputError for invalid inputs.
    """
    if outcome == "refined":
        if type_label is None:
            raise gh.InvalidInputError("type_label is required when outcome='refined'")
        transition = refined(type_label)
    elif outcome == "needs-attention":
        transition = refinement_needs_attention()
    else:
        raise gh.InvalidInputError("outcome must be 'refined' or 'needs-attention'")
    apply_transition(repo, issue, transition)
    return f"Refinement outcome '{outcome}' applied to issue #{issue}"


def apply_estimation(
    repo: str,
    issue: int,
    outcome: str,
    blast_radius: str | None = None,
    touch: str | None = None,
    human_involvement: str | None = None,
    review_overhead: str | None = None,
) -> str:
    """Apply the lifecycle label transition after estimation.

    estimated      → rolls the four Low|Mid|High scores into a size:* label.
    needs-attention → transitions issue to status:needs-attention.
    Raises gh.InvalidInputError for invalid inputs; ValueError for bad scores.
    """
    if outcome == "estimated":
        if None in (blast_radius, touch, human_involvement, review_overhead):
            raise gh.InvalidInputError(
                "blast_radius, touch, human_involvement, and review_overhead are all required when outcome='estimated'"
            )
        size = roll_up_size(blast_radius, touch, human_involvement, review_overhead)  # type: ignore[arg-type]
        transition = estimated(size)
        apply_transition(repo, issue, transition)
        return f"Estimation outcome 'estimated' applied to issue #{issue} ({size_label(size)})"
    if outcome == "needs-attention":
        apply_transition(repo, issue, estimation_needs_attention())
        return f"Estimation outcome 'needs-attention' applied to issue #{issue}"
    raise gh.InvalidInputError("outcome must be 'estimated' or 'needs-attention'")


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="pipeline.entrypoint labels")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("issue-labels")
    p.add_argument("issue", type=int)

    p = sub.add_parser("pr-labels")
    p.add_argument("pr", type=int)

    p = sub.add_parser("set-issue-status")
    p.add_argument("issue", type=int)
    p.add_argument("target")

    p = sub.add_parser("edit-issue-labels")
    p.add_argument("issue", type=int)
    p.add_argument("--add", action="append", default=[])
    p.add_argument("--remove", action="append", default=[])

    p = sub.add_parser("set-pr-label")
    p.add_argument("pr", type=int)
    p.add_argument("target", nargs="?", default=None)

    p = sub.add_parser("escalate-pr")
    p.add_argument("pr", type=int)

    args = parser.parse_args(argv)

    if args.command == "issue-labels":
        print(",".join(issue_labels(ctx.repo, args.issue)))
    elif args.command == "pr-labels":
        print(",".join(pr_labels(ctx.repo, args.pr)))
    elif args.command == "set-issue-status":
        set_issue_status(ctx.repo, args.issue, args.target)
    elif args.command == "edit-issue-labels":
        edit_issue_labels(ctx.repo, args.issue, add=args.add, remove=args.remove)
    elif args.command == "set-pr-label":
        set_pr_pipeline_label(ctx.repo, args.pr, args.target)
    elif args.command == "escalate-pr":
        escalate_pr(ctx.repo, args.pr)
    return 0
