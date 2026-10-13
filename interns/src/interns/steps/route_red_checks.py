"""A red PR check goes straight to a human, no coder retry loop (#133).

Only the PR is escalated; the issue keeps its status because the work is in a PR awaiting a human (#289).
"""

from __future__ import annotations

from .. import cli
from ..ctx import ActionsCtx
from ..domain import lifecycle, lifecycle_apply


def route_red_checks(repo: str, pr: int, reason: str, *, run_url: str = "") -> None:
    outcome = lifecycle.decide(lifecycle.Event.RED_CHECKS, lifecycle.Facts(has_issue=False, has_pr=True))
    lifecycle_apply.apply(repo, outcome, pr=pr, issue=None, words=lifecycle_apply.Words(run_url=run_url, detail=reason))


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("route-red-checks")
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
