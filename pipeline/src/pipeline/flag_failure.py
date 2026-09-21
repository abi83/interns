"""Common failure handler for the agent phases: send the issue to
status:needs-attention, mark the PR pr:needs-attention (or just clear its
label on a fix-round crash, which escalates issue-side), and post a comment
linking the run.
"""

from __future__ import annotations

import sys

from . import actions_env, cli, gh, labels


def flag_failure(repo: str, noun: str, issue: int | None, pr: int | None, fix_round: bool) -> None:
    # A review-job crash leaves the PR stuck with no verdict; mark it for a
    # human. A fix-round crash escalates on the issue side, so the PR just
    # loses its label.
    if pr is not None:
        if fix_round:
            labels.set_pr_pipeline_label(repo, pr)
        else:
            labels.escalate_pr(repo, pr)
    if issue is not None:
        labels.set_issue_status(repo, issue, labels.STATUS_NEEDS_ATTENTION)

    if fix_round:
        if issue is None:
            raise ValueError("--fix-round requires --issue")
        gh.issue_comment(
            repo, issue,
            "Automated fix round failed — issue set to `status:needs-attention`. "
            f"Re-dispatch once the cause is addressed: `gh workflow run code-pipeline.yml "
            f"-f phase=coder -f issue_number={issue} -f fix_round=true`. Run: {actions_env.run_url(repo)}",
        )
        return

    body = f"Automated {noun} failed. See the run: {actions_env.run_url(repo)}"
    if pr is not None:
        gh.pr_comment(repo, pr, body)
    else:
        if issue is None:
            raise ValueError("one of --issue or --pr is required")
        gh.issue_comment(repo, issue, body)


def _main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pipeline.flag_failure")
    parser.add_argument("--noun", default="")
    parser.add_argument("--issue", default="")
    parser.add_argument("--pr", default="")
    parser.add_argument("--fix-round", action="store_true")
    args = parser.parse_args(argv)

    flag_failure(
        cli.require_env("GITHUB_REPOSITORY"),
        args.noun,
        cli.optional_int(args.issue),
        cli.optional_int(args.pr),
        args.fix_round,
    )
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(_main))
