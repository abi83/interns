"""Hard ceiling on automatic reviewer runs for one PR, independent of the fix-loop
cap in apply_verdict. After the loop escalates, every push still spawns a full
reviewer run; without a ceiling a many-commit PR is unbounded spend.

Counts the reviewer bot's prior reviews. At or over the cap the PR goes to
pr:needs-attention with a one-line notice. workflow_dispatch (a human override)
never calls this module.
"""

from __future__ import annotations

from . import lifecycle, lifecycle_apply, verdict


def check_cap(repo: str, pr: int, reviewer_bot: str, max_reviews: int, *, count: int | None = None,
              run_url: str = "") -> bool:
    """True when the PR is at or over the cap -- escalates and comments in
    that case. False (a no-op) otherwise.

    `count` lets a caller that already fetched the reviewer's review count
    this run (the review plan's dedup check, one step earlier) pass it
    straight through instead of this function fetching it all over again --
    the two would otherwise hit the same `pulls/{pr}/reviews` endpoint twice
    in the same run. Omit it to fetch fresh, e.g. for a standalone call."""
    if count is None:
        count = len(verdict.reviews_by(repo, pr, reviewer_bot))
    if count < max_reviews:
        return False
    outcome = lifecycle.decide(lifecycle.Event.REVIEW_CAP_REACHED, lifecycle.Facts(has_issue=False, has_pr=True))
    words = lifecycle_apply.Words(run_url=run_url, detail=str(max_reviews))
    lifecycle_apply.apply(repo, outcome, pr=pr, issue=None, words=words)
    return True
