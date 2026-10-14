"""Runs when a coder/reviewer PR closes. Nothing else in the pipeline reacts
to a close, so without this the linked issue keeps status:in-progress
forever: on a merge GitHub's `Closes #N` shuts the issue but leaves the
label, and an unmerged close leaves the issue open with no agent owning it.

  merged            -> drop status:in-progress from the (already closed) issue
  closed, unmerged  -> move the issue status:in-progress -> status:needs-attention
                       and comment that a human needs to decide what happens next

Either way, clear any stale pr:* label from the PR.
"""

from __future__ import annotations

from .. import cli
from ..ctx import ActionsCtx
from ..domain import lifecycle, lifecycle_apply
from ..env_spec import EnvSpec

ENV_SPEC = EnvSpec.of("GITHUB_RUN_ID")


def handle_pr_closed(repo: str, pr: int, issue: int | None, merged: bool, *, server_url: str, run_url: str) -> None:
    event = lifecycle.Event.PR_CLOSED_MERGED if merged else lifecycle.Event.PR_CLOSED_UNMERGED
    outcome = lifecycle.decide(event, lifecycle.Facts(has_issue=issue is not None, has_pr=True))
    lifecycle_apply.apply(repo, outcome, pr=pr, issue=issue, words=lifecycle_apply.Words(run_url=run_url, server_url=server_url))


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("handle-pr-closed")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--issue", default="")
    parser.add_argument("--merged", required=True)
    args = parser.parse_args(argv)

    handle_pr_closed(
        ctx.repo,
        args.pr,
        cli.optional_int(args.issue),
        args.merged == "true",
        server_url=ctx.server_url,
        run_url=ctx.run_url(),
    )
    return 0
