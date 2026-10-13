"""Reviewer-verdict and CHANGES_REQUESTED-round queries.

Unifies three independently-written "reviewer's last review state against
current head" queries (interns.steps.apply_verdict, interns.run_summary,
interns.steps.check_review_cap -- interns#157) into one place.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from .. import gh


class ReviewState(StrEnum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    COMMENTED = "COMMENTED"
    DISMISSED = "DISMISSED"
    PENDING = "PENDING"


@dataclass(frozen=True)
class Review:
    login: str
    state: ReviewState
    commit_id: str


@dataclass(frozen=True)
class FullReview(Review):
    """What `all_reviews` fetches. Only gather_fix_feedback reads the extra
    fields; callers that need just the verdict take the narrower `Review`."""

    id: int
    submitted_at: str
    body: str


def all_reviews(repo: str, pr: int) -> list[FullReview]:
    """Every review on `pr`, across every page, regardless of author, oldest
    first (GitHub's own order) -- e.g. for run-summary's coder-phase fix-round
    count, which counts CHANGES_REQUESTED from any reviewer, not just
    REVIEWER_BOT."""
    data = gh.pr_reviews(repo, pr)
    if not isinstance(data, list):
        raise gh.GhCommandError(f"unexpected reviews payload for {repo}#{pr}")
    return [
        FullReview(
            login=r["user"]["login"],
            state=ReviewState(r["state"]),
            commit_id=r["commit_id"],
            id=r["id"],
            submitted_at=r["submitted_at"],
            body=r["body"] or "",
        )
        for r in data
    ]


def reviews_by(repo: str, pr: int, login: str) -> list[FullReview]:
    """`login`'s reviews on `pr`, oldest first (GitHub's own order)."""
    return [r for r in all_reviews(repo, pr) if r.login == login]


def verdict_for_head(reviews: Sequence[Review], head_sha: str) -> ReviewState | None:
    """The reviewer's verdict for `head_sha`: the state of their latest
    review, or None when that review targets an earlier commit -- a stale
    review left over from a round a later push already addressed."""
    if not reviews:
        return None
    last = reviews[-1]
    return last.state if last.commit_id == head_sha else None


def rounds_requested(reviews: Sequence[Review], *, exclude_commit: str | None = None) -> int:
    """How many CHANGES_REQUESTED reviews there have been, optionally
    excluding ones against `exclude_commit` (e.g. this run's own verdict,
    already posted against the PR's current head)."""
    return sum(
        1 for r in reviews
        if r.state == ReviewState.CHANGES_REQUESTED and r.commit_id != exclude_commit
    )
