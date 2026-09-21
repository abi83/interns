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

import sys

from . import actions_env, gh, labels, verdict

MAX_FIX_ROUNDS = 1


def apply_verdict(repo: str, pr: int, issue: int | None, reviewer_bot: str) -> None:
    head_sha = gh.pr_view(repo, pr, ["headRefOid"])["headRefOid"]
    reviews = verdict.reviews_by(repo, pr, reviewer_bot)
    last_state = verdict.verdict_for_head(reviews, head_sha)

    if last_state == "APPROVED":
        labels.set_pr_pipeline_label(repo, pr)
        if issue is not None:
            gh.issue_comment(
                repo, issue,
                f"Reviewer approved [PR #{pr}]({actions_env.pr_url(repo, pr)}) — awaiting owner merge. "
                f"Run: {actions_env.run_url(repo)}",
            )
        return

    if last_state == "CHANGES_REQUESTED":
        rounds = verdict.rounds_requested(reviews)
        if rounds > MAX_FIX_ROUNDS:
            labels.escalate_pr(repo, pr)
            if issue is not None:
                labels.set_issue_status(repo, issue, "status:needs-attention")
            gh.pr_comment(
                repo, pr,
                "Second review still requests changes — the automatic fix round didn't converge. "
                f"Escalating to a human. See the run: {actions_env.run_url(repo)}",
            )
        elif issue is not None:
            labels.set_pr_pipeline_label(repo, pr, "pr:coding")
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
                f"automatically. See the run: {actions_env.run_url(repo)}",
            )
        return

    labels.escalate_pr(repo, pr)
    if issue is not None:
        labels.set_issue_status(repo, issue, "status:needs-attention")
    gh.pr_comment(
        repo, pr,
        "Review run completed without submitting a recognized verdict — likely stopped partway through. "
        f"See the run: {actions_env.run_url(repo)}",
    )


def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="python -m pipeline.apply_verdict")
    parser.add_argument("pr", type=int)
    parser.add_argument("issue", nargs="?", default="")
    args = parser.parse_args(argv)

    apply_verdict(
        os.environ["GITHUB_REPOSITORY"],
        args.pr,
        int(args.issue) if args.issue else None,
        os.environ["REVIEWER_BOT"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
