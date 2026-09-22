"""A red PR check goes straight to a human, no coder retry loop (#133).
"""

from __future__ import annotations

from . import cli, gh, labels
from .ctx import ActionsCtx


def route_red_checks(repo: str, pr: int, issue: int | None, reason: str, *, run_url: str = "") -> None:
    labels.escalate_pr(repo, pr)
    gh.pr_comment(
        repo, pr,
        f"PR checks are not green ({reason}) — the reviewer won't run. The coder writes and runs "
        "tests before pushing, so this is being sent straight to a human rather than retried. "
        f"Run: {run_url}",
    )
    if issue is not None:
        labels.set_issue_status(repo, issue, labels.STATUS_NEEDS_ATTENTION)


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="interns.entrypoint route-red-checks")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--issue", default="")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)

    route_red_checks(
        ctx.repo,
        args.pr,
        cli.optional_int(args.issue),
        args.reason,
        run_url=ctx.run_url(),
    )
    return 0
