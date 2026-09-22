"""Reviewer-verdict and CHANGES_REQUESTED-round queries.

Unifies three independently-written "reviewer's last review state against
current head" queries (pipeline.apply_verdict, pipeline.run_summary,
pipeline.check_review_cap -- interns#157) into one place.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import gh
from .ctx import ActionsCtx


@dataclass(frozen=True)
class Review:
    login: str
    state: str
    commit_id: str
    # Only pipeline.gather_fix_feedback needs these; every other caller here
    # only cares about login/state/commit_id. Defaulted rather than split
    # into a second type so there's still exactly one review fetch to keep
    # paginated and in sync (interns#180 review).
    id: int = 0
    submitted_at: str = ""
    body: str = ""


def all_reviews(repo: str, pr: int) -> list[Review]:
    """Every review on `pr`, across every page, regardless of author, oldest
    first (GitHub's own order) -- e.g. for run-summary's coder-phase fix-round
    count, which counts CHANGES_REQUESTED from any reviewer, not just
    REVIEWER_BOT."""
    data = gh.api_all_pages(f"repos/{repo}/pulls/{pr}/reviews")
    if not isinstance(data, list):
        raise gh.GhCommandError(f"unexpected reviews payload for {repo}#{pr}")
    return [
        Review(
            login=r.get("user", {}).get("login", ""),
            state=r["state"],
            commit_id=r.get("commit_id", ""),
            id=r.get("id", 0),
            submitted_at=r.get("submitted_at") or "",
            body=r.get("body") or "",
        )
        for r in data
    ]


def reviews_by(repo: str, pr: int, login: str) -> list[Review]:
    """`login`'s reviews on `pr`, oldest first (GitHub's own order)."""
    return [r for r in all_reviews(repo, pr) if r.login == login]


def verdict_for_head(reviews: list[Review], head_sha: str) -> str | None:
    """The reviewer's verdict for `head_sha`: the state of their latest
    review, or None when that review targets an earlier commit -- a stale
    review left over from a round a later push already addressed."""
    if not reviews:
        return None
    last = reviews[-1]
    return last.state if last.commit_id == head_sha else None


def rounds_requested(reviews: list[Review], *, exclude_commit: str | None = None) -> int:
    """How many CHANGES_REQUESTED reviews there have been, optionally
    excluding ones against `exclude_commit` (e.g. this run's own verdict,
    already posted against the PR's current head)."""
    return sum(
        1 for r in reviews
        if r.state == "CHANGES_REQUESTED" and r.commit_id != exclude_commit
    )


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="pipeline.entrypoint verdict")
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
    reviews = reviews_by(ctx.repo, args.pr, login)

    if args.command == "verdict-for-head":
        print(verdict_for_head(reviews, args.head_sha) or "")
    elif args.command == "rounds-requested":
        print(rounds_requested(reviews, exclude_commit=args.exclude_commit))
    elif args.command == "review-count":
        print(len(reviews))
    elif args.command == "summary-for-head":
        print(f"verdict={verdict_for_head(reviews, args.head_sha) or ''}")
        print(f"count={len(reviews)}")
    return 0
