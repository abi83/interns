"""Acts on the reviewer's latest verdict on a PR.

Issue status:* is coarse: status:in-progress for the whole run,
status:needs-attention when a human is needed, closed on merge. There is no
"approved" issue state -- an approved PR is found via its native review
state, and the pr:* label only marks which agent is currently working (none,
once the reviewer is done) or pr:needs-attention when the loop has given up.
The fix-round decision is read from the verdict, not a label.

MAX_FIX_ROUNDS: how many automatic coder fix rounds a PR gets before the loop
escalates to a human. Counts CHANGES_REQUESTED reviews (this run's verdict
included). Distinct from interns.yml's max_turns (turns inside one agent
run) -- this counts whole agent invocations across a PR, so it stays a
workflow-behaviour constant here, not an execution limit in the config file.
"""

from __future__ import annotations

from . import cli, gh, labels, verdict
from .ctx import ActionsCtx

MAX_FIX_ROUNDS = 1


def apply_verdict(repo: str, pr: int, issue: int | None, reviewer_bot: str, *, server_url: str = "", run_url: str = "") -> None:
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
        if rounds > MAX_FIX_ROUNDS:
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

    parser = argparse.ArgumentParser(prog="interns.entrypoint apply-verdict")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--issue", default="")
    args = parser.parse_args(argv)

    apply_verdict(
        ctx.repo,
        args.pr,
        cli.optional_int(args.issue),
        ctx.reviewer_bot,
        server_url=ctx.server_url,
        run_url=ctx.run_url(),
    )
    return 0
