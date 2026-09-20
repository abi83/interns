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

from . import gh

ISSUE_STATUS_LABELS = ("status:in-progress", "status:needs-attention", "status:ready")
PR_PIPELINE_LABELS = ("pr:coding", "pr:in-review", "pr:needs-attention")


def _best_effort(action: str, fn, *args, **kwargs) -> None:
    try:
        fn(*args, **kwargs)
    except gh.GhCommandError as exc:
        print(f"warning: {action} failed, continuing: {exc}", file=sys.stderr)


def issue_labels(repo: str, issue: int) -> list[str]:
    return [label["name"] for label in gh.issue_view(repo, issue, ["labels"])["labels"]]


def pr_labels(repo: str, pr: int) -> list[str]:
    return [label["name"] for label in gh.pr_view(repo, pr, ["labels"])["labels"]]


def edit_issue_labels(repo: str, issue: int, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None:
    """Add/remove specific issue labels, skipping any already in the wanted
    state -- in particular a `remove` that isn't present, which `gh` would
    otherwise reject."""
    current = set(issue_labels(repo, issue))
    add_labels = [label for label in add if label not in current]
    remove_labels = [label for label in remove if label in current]
    if add_labels or remove_labels:
        _best_effort("issue label edit", gh.issue_edit, repo, issue, add_labels=add_labels, remove_labels=remove_labels)


def edit_pr_labels(repo: str, pr: int, add: Sequence[str] = (), remove: Sequence[str] = ()) -> None:
    """Add/remove specific PR labels, skipping any already in the wanted
    state -- in particular a `remove` that isn't present, which `gh` would
    otherwise reject."""
    current = set(pr_labels(repo, pr))
    add_labels = [label for label in add if label not in current]
    remove_labels = [label for label in remove if label in current]
    if add_labels or remove_labels:
        _best_effort("PR label edit", gh.pr_edit, repo, pr, add_labels=add_labels, remove_labels=remove_labels)


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
    set_pr_pipeline_label(repo, pr, "pr:needs-attention")


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
    sys.exit(_main(sys.argv[1:]))
