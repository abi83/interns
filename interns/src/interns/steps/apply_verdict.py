"""Acts on the reviewer's latest verdict on a PR.

Issue status:* is coarse: status:in-progress for the whole run,
status:needs-attention when a human is needed, closed on merge. There is no
"approved" issue state -- an approved PR is found via its native review
state, and the pr:* label only marks which agent is currently working (none,
once the reviewer is done) or pr:needs-attention when the loop has given up.
The fix-round decision is read from the verdict, not a label.
"""

from __future__ import annotations

from .. import cli, config, gh, verdict
from . import labels
from ..ctx import ActionsCtx


def apply_verdict(repo: str, pr: int, issue: int | None, reviewer_bot: str, *, max_fix_rounds: int, server_url: str = "", run_url: str = "") -> None:
    head_sha = gh.pr_view(repo, pr, ["headRefOid"])["headRefOid"]
    reviews = verdict.reviews_by(repo, pr, reviewer_bot)
    last_state = verdict.verdict_for_head(reviews, head_sha)

    if last_state == "APPROVED":
        labels.set_pr_pipeline_label(repo, pr)
        if issue is not None:
            gh.issue_comment(
                repo, issue,
                f"Reviewer approved [PR #{pr}]({server_url}/{repo}/pull/{pr}) — awaiting owner merge. "
                f"Run: {run_url}",
            )
        return

    if last_state == "CHANGES_REQUESTED":
        rounds = verdict.rounds_requested(reviews)
        if rounds > max_fix_rounds:
            labels.escalate_pr(repo, pr)
            if issue is not None:
                labels.set_issue_status(repo, issue, labels.STATUS_NEEDS_ATTENTION)
            gh.pr_comment(
                repo, pr,
                "Second review still requests changes — the automatic fix round didn't converge. "
                f"Escalating to a human. See the run: {run_url}",
            )
        elif issue is not None:
            labels.set_pr_pipeline_label(repo, pr, labels.PR_CODING)
            # GITHUB_TOKEN label edits don't fire workflow runs (anti-recursion), so
            # dispatch the coder explicitly as a fix round.
            gh.dispatch_workflow(
                repo, "code-pipeline.yml", None,
                {"phase": "coder", "issue_number": str(issue), "fix_round": "true"},
            )
        else:
            labels.set_pr_pipeline_label(repo, pr)
            gh.pr_comment(
                repo, pr,
                "Changes requested but this PR has no linked issue — can't dispatch a coder fix round "
                f"automatically. See the run: {run_url}",
            )
        return

    labels.escalate_pr(repo, pr)
    if issue is not None:
        labels.set_issue_status(repo, issue, labels.STATUS_NEEDS_ATTENTION)
    gh.pr_comment(
        repo, pr,
        "Review run completed without submitting a recognized verdict — likely stopped partway through. "
        f"See the run: {run_url}",
    )


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="interns.entrypoint apply-verdict")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--issue", default="")
    args = parser.parse_args(argv)

    config_path = os.environ.get("INTERNS_CONFIG", ".github/interns.yml")
    rl = config.review_loop_config(config.load_raw(config_path), config_path)

    apply_verdict(
        ctx.repo,
        args.pr,
        cli.optional_int(args.issue),
        ctx.reviewer_bot,
        max_fix_rounds=rl.max_fix_rounds,
        server_url=ctx.server_url,
        run_url=ctx.run_url(),
    )
    return 0
