"""Hard ceiling on automatic reviewer runs for one PR, independent of the
coder<->reviewer fix-loop cap in apply_verdict. After the fix loop escalates,
every further push still spawns a full LLM reviewer run; without a ceiling
that is unbounded spend on a PR that takes many commits to land.

Counts the reviewer bot's own prior reviews on the PR. At or over the cap it
escalates the PR to pr:needs-attention and posts a one-line notice so it
stays discoverable.

workflow_dispatch is an explicit human override and never calls this module.
"""

from __future__ import annotations

import sys

from . import gh, labels, verdict


def check_cap(repo: str, pr: int, reviewer_bot: str, max_reviews: int, *, count: int | None = None) -> bool:
    """True when the PR is at or over the cap -- escalates and comments in
    that case. False (a no-op) otherwise.

    `count` lets a caller that already fetched the reviewer's review count
    this run (the reviewer job's dedup check, one job earlier) pass it
    straight through instead of this function fetching it all over again --
    the two would otherwise hit the same `pulls/{pr}/reviews` endpoint twice
    in the same run. Omit it to fetch fresh, e.g. for a standalone call."""
    if count is None:
        count = len(verdict.reviews_by(repo, pr, reviewer_bot))
    if count < max_reviews:
        return False
    labels.escalate_pr(repo, pr)
    gh.pr_comment(
        repo, pr,
        f"Automatic review limit ({max_reviews}) reached — further review is manual. Run: {gh.run_url(repo)}",
    )
    return True


def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="python -m pipeline.check_review_cap")
    parser.add_argument("pr", type=int)
    parser.add_argument("--count", type=int, default=None,
                         help="skip the review-count fetch and use this instead")
    args = parser.parse_args(argv)

    max_reviews = int(os.environ.get("MAX_AUTOMATIC_REVIEWS_PER_PR", "5"))
    capped = check_cap(os.environ["GITHUB_REPOSITORY"], args.pr, os.environ["REVIEWER_BOT"], max_reviews,
                        count=args.count)
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"capped={'true' if capped else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
