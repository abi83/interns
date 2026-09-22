"""Checks out a PR's branch and writes the latest review round to
$GITHUB_OUTPUT as `text` for the coder fix-round prompt: the most recent
CHANGES_REQUESTED review, its line-anchored comments, and any conversation
posted after it. Earlier rounds are already addressed in prior commits --
feeding them back in makes the coder re-litigate resolved points.
"""

from __future__ import annotations

import subprocess
import sys

from . import cli, gh, verdict
from .ctx import ActionsCtx


class NoChangesRequestedReviewError(RuntimeError):
    """The PR has no CHANGES_REQUESTED review to gather feedback from."""


def checkout_branch(head_ref: str) -> None:
    subprocess.run(["git", "fetch", "origin", head_ref], check=True)
    subprocess.run(["git", "checkout", head_ref], check=True)


def _latest_changes_requested_review(repo: str, pr: int) -> verdict.Review:
    # Any reviewer's CHANGES_REQUESTED counts here, not just REVIEWER_BOT's --
    # unlike apply_verdict/check_review_cap, which only ever act on the bot's
    # own verdict. Routed through verdict.all_reviews rather than a second,
    # independent fetch so this and those three stay paginated the same way
    # and can't disagree about which review is "latest" (interns#180 review).
    reviews = [r for r in verdict.all_reviews(repo, pr) if r.state == "CHANGES_REQUESTED"]
    if not reviews:
        raise NoChangesRequestedReviewError(f"no CHANGES_REQUESTED review found for PR #{pr}")
    return reviews[-1]


def build_feedback_text(repo: str, pr: int) -> str:
    review = _latest_changes_requested_review(repo, pr)

    comments = sorted(
        (c for c in gh.api_all_pages(f"repos/{repo}/pulls/{pr}/comments")
         if str(c.get("pull_request_review_id")) == str(review.id)),
        key=lambda c: c["created_at"],
    )
    conversation = sorted(
        (c for c in gh.api_all_pages(f"repos/{repo}/issues/{pr}/comments") if c["created_at"] > review.submitted_at),
        key=lambda c: c["created_at"],
    )

    lines = [
        f"## Latest REQUEST_CHANGES review — {review.submitted_at}",
        "",
        review.body or "(no summary body)",
        "",
        "## Inline comments on that review",
    ]
    for c in comments:
        line_no = c.get("line") or c.get("original_line") or "?"
        lines.append(f"- {c['path']}:{line_no}\n  {c['body']}")
    lines += ["", "## PR conversation posted after that review"]
    for c in conversation:
        lines.append(f"### {c['user']['login']} ({c['created_at']})\n{c['body']}")
    return "\n".join(lines)


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="interns.entrypoint gather-fix-feedback")
    parser.add_argument("--pr", required=True)
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--issue", required=True)
    args = parser.parse_args(argv)

    if not args.pr:
        print(f"error: --pr is required (no open PR for issue #{args.issue})", file=sys.stderr)
        return 1

    pr = int(args.pr)
    checkout_branch(args.head_ref)

    try:
        text = build_feedback_text(ctx.repo, pr)
    except NoChangesRequestedReviewError as exc:
        print(f"Error: fix round for PR #{pr} but {exc}", file=sys.stderr)
        return 1

    cli.append_output(cli.github_output_block("text", text.encode()))
    return 0
