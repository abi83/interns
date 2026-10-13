"""Runs after a successful coder phase. If a PR now references the issue,
hand it to the reviewer (the issue stays status:in-progress for the whole
active run -- the pr:* label is the only "which agent" signal, and a red
check or rejection is read from native PR state, not a label). If no PR was
left, the agent stopped for clarification or partway through -- flag it for
a human.
"""

from __future__ import annotations

from .. import cli
from ..ctx import ActionsCtx
from ..domain import lifecycle, lifecycle_apply


def handoff(repo: str, issue: int, pr: int | None, *, run_url: str = "") -> None:
    event = lifecycle.Event.CODER_NO_PR if pr is None else lifecycle.Event.CODER_HANDOFF
    outcome = lifecycle.decide(event, lifecycle.Facts(has_issue=True, has_pr=pr is not None))
    lifecycle_apply.apply(repo, outcome, pr=pr, issue=issue, words=lifecycle_apply.Words(run_url=run_url))


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("handoff-to-review")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--pr", default="")
    args = parser.parse_args(argv)

    handoff(ctx.repo, args.issue, cli.optional_int(args.pr), run_url=ctx.run_url())
    return 0
