"""`verdict` command: the reviewer's verdict and CHANGES_REQUESTED round count."""

from __future__ import annotations

import argparse

from ..ctx import ActionsCtx
from ..domain import verdict


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="interns.entrypoint verdict")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--login", default="")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("verdict-for-head")
    p.add_argument("head_sha")

    p = sub.add_parser("rounds-requested")
    p.add_argument("--exclude-commit", default=None)

    sub.add_parser("review-count")

    # verdict-for-head + review-count in one fetch, for a caller (the
    # reviewer job's dedup check) that needs both and would otherwise hit
    # `pulls/{pr}/reviews` twice for data that doesn't change between the
    # two queries.
    p = sub.add_parser("summary-for-head")
    p.add_argument("head_sha")

    args = parser.parse_args(argv)
    login = args.login or ctx.reviewer_bot
    reviews = verdict.reviews_by(ctx.repo, args.pr, login)

    if args.command == "verdict-for-head":
        print(verdict.verdict_for_head(reviews, args.head_sha) or "")
    elif args.command == "rounds-requested":
        print(verdict.rounds_requested(reviews, exclude_commit=args.exclude_commit))
    elif args.command == "review-count":
        print(len(reviews))
    elif args.command == "summary-for-head":
        print(f"verdict={verdict.verdict_for_head(reviews, args.head_sha) or ''}")
        print(f"count={len(reviews)}")
    return 0
