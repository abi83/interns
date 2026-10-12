"""`labels` command: label reads and edits for workflow shell steps."""

from __future__ import annotations

import argparse
from collections.abc import Callable

from .. import cli
from ..ctx import ActionsCtx
from ..domain import labels


def _parser() -> argparse.ArgumentParser:
    parser = cli.build_parser("labels")
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
    return parser


def _issue_labels(ctx: ActionsCtx, args: argparse.Namespace) -> None:
    print(",".join(labels.issue_labels(ctx.repo, args.issue)))


def _pr_labels(ctx: ActionsCtx, args: argparse.Namespace) -> None:
    print(",".join(labels.pr_labels(ctx.repo, args.pr)))


def _set_issue_status(ctx: ActionsCtx, args: argparse.Namespace) -> None:
    labels.set_issue_status(ctx.repo, args.issue, args.target)


def _edit_issue_labels(ctx: ActionsCtx, args: argparse.Namespace) -> None:
    labels.edit_issue_labels(ctx.repo, args.issue, add=args.add, remove=args.remove)


def _set_pr_label(ctx: ActionsCtx, args: argparse.Namespace) -> None:
    labels.set_pr_pipeline_label(ctx.repo, args.pr, args.target)


def _escalate_pr(ctx: ActionsCtx, args: argparse.Namespace) -> None:
    labels.escalate_pr(ctx.repo, args.pr)


_SUBCOMMANDS: dict[str, Callable[[ActionsCtx, argparse.Namespace], None]] = {
    "issue-labels": _issue_labels,
    "pr-labels": _pr_labels,
    "set-issue-status": _set_issue_status,
    "edit-issue-labels": _edit_issue_labels,
    "set-pr-label": _set_pr_label,
    "escalate-pr": _escalate_pr,
}


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    _SUBCOMMANDS[args.command](ctx, args)
    return 0
