"""`verdict` command: the reviewer's verdict and CHANGES_REQUESTED round count."""

from __future__ import annotations

import argparse
from collections.abc import Callable

from .. import cli
from ..ctx import ActionsCtx
from ..domain import verdict
from ..domain.verdict import FullReview


def _verdict_for_head(reviews: list[FullReview], args: argparse.Namespace) -> list[str]:
    return [verdict.verdict_for_head(reviews, args.head_sha) or ""]


def _rounds_requested(reviews: list[FullReview], args: argparse.Namespace) -> list[str]:
    return [str(verdict.rounds_requested(reviews, exclude_commit=args.exclude_commit))]


def _review_count(reviews: list[FullReview], args: argparse.Namespace) -> list[str]:
    return [str(len(reviews))]


_SUBCOMMANDS: dict[str, Callable[[list[FullReview], argparse.Namespace], list[str]]] = {
    "verdict-for-head": _verdict_for_head,
    "rounds-requested": _rounds_requested,
    "review-count": _review_count,
}


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("verdict")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--login", default="")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("verdict-for-head")
    p.add_argument("head_sha")

    p = sub.add_parser("rounds-requested")
    p.add_argument("--exclude-commit", default=None)

    sub.add_parser("review-count")

    args = parser.parse_args(argv)
    reviews = verdict.reviews_by(ctx.repo, args.pr, args.login or ctx.reviewer_bot)
    for line in _SUBCOMMANDS[args.command](reviews, args):
        print(line)
    return 0
