"""A red PR check goes straight to a human, no coder retry loop (#133).

Only the PR is escalated; the issue keeps its status because the work is in a PR awaiting a human (#289).
"""

from __future__ import annotations

from .. import gh
from . import labels
from ..ctx import ActionsCtx


def route_red_checks(repo: str, pr: int, reason: str, *, run_url: str = "") -> None:
    labels.escalate_pr(repo, pr)
    gh.pr_comment(
        repo, pr,
        f"PR checks are not green ({reason}) — the reviewer won't run, so this is sent straight to a "
        "human rather than retried. The coder can only verify its work through your Makefile: make sure "
        "it has real `setup`, `test` and `build` targets (stubs are skipped), otherwise the coder "
        "cannot catch failures before pushing. "
        f"Run: {run_url}",
    )


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="interns.entrypoint route-red-checks")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args(argv)

    route_red_checks(
        ctx.repo,
        args.pr,
        args.reason,
        run_url=ctx.run_url(),
    )
    return 0
