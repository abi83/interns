"""Reviewer-verdict and CHANGES_REQUESTED-round queries.

Unifies three independently-written "reviewer's last review state against
current head" queries (apply-verdict.sh, run-summary.sh, check-review-cap.sh
-- interns#157) into one place.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from . import gh


@dataclass(frozen=True)
class Review:
    login: str
    state: str
    commit_id: str


def reviews_by(repo: str, pr: int, login: str) -> list[Review]:
    """`login`'s reviews on `pr`, oldest first (GitHub's own order)."""
    data = gh.api(f"repos/{repo}/pulls/{pr}/reviews?per_page=100")
    if not isinstance(data, list):
        raise gh.GhCommandError(f"unexpected reviews payload for {repo}#{pr}")
    return [
        Review(login=r["user"]["login"], state=r["state"], commit_id=r.get("commit_id", ""))
        for r in data
        if r.get("user", {}).get("login") == login
    ]


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


def _main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pipeline.verdict")
    parser.add_argument("repo")
    parser.add_argument("pr", type=int)
    parser.add_argument("login")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("verdict-for-head")
    p.add_argument("head_sha")

    p = sub.add_parser("rounds-requested")
    p.add_argument("--exclude-commit", default=None)

    sub.add_parser("review-count")

    args = parser.parse_args(argv)
    reviews = reviews_by(args.repo, args.pr, args.login)

    if args.command == "verdict-for-head":
        print(verdict_for_head(reviews, args.head_sha) or "")
    elif args.command == "rounds-requested":
        print(rounds_requested(reviews, exclude_commit=args.exclude_commit))
    elif args.command == "review-count":
        print(len(reviews))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
