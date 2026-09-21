"""Issue/PR pipeline label state machine.

Label edits here are best-effort: a transient `gh` failure (rate limit, a
concurrent edit) shouldn't abort the calling workflow step over a label that a
later run will just re-set. `_best_effort` is the one place that swallows
`GhCommandError`, and everything in this module routes through it -- no
scattered `|| true` / bare `except` with its own judgment call.

That's also what makes the "target label not already present" case cheap:
every transition reads current labels first and only issues `--add-label` /
`--remove-label` for labels that actually need to change, so removing an
absent label -- which `gh` would reject -- never happens in the first place.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import NamedTuple

from . import cli, gh

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


def _best_effort(action: str, fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except gh.GhCommandError as exc:
        print(f"warning: {action} failed, continuing: {exc}", file=sys.stderr)


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
    _best_effort("issue label edit", edit_issue_labels_strict, repo, issue, add, remove)


def edit_pr_labels(repo: str, pr: int, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None:
    """PR counterpart of `edit_issue_labels` (always best-effort)."""
    add_labels, remove_labels = _changed_labels(pr_labels(repo, pr), add, remove)
    if add_labels or remove_labels:
        _best_effort("PR label edit", gh.pr_edit, repo, pr, add_labels=add_labels, remove_labels=remove_labels)


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


def _main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pipeline.labels")
    parser.add_argument("repo")
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
        print(",".join(issue_labels(args.repo, args.issue)))
    elif args.command == "pr-labels":
        print(",".join(pr_labels(args.repo, args.pr)))
    elif args.command == "set-issue-status":
        set_issue_status(args.repo, args.issue, args.target)
    elif args.command == "edit-issue-labels":
        edit_issue_labels(args.repo, args.issue, add=args.add, remove=args.remove)
    elif args.command == "set-pr-label":
        set_pr_pipeline_label(args.repo, args.pr, args.target)
    elif args.command == "escalate-pr":
        escalate_pr(args.repo, args.pr)
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(_main))
