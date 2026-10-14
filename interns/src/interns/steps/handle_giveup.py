"""Runs after a coder fix round. If the agent left a ./.coder-gave-up.md
sentinel it has *declined* the task -- the feedback needs a protected path
it can't push, is out of scope for the issue, or needs an owner decision --
rather than pushing a fix. Escalate straight to a human instead of handing
the PR back to the reviewer for a wasted round.

The coder step still exits 0 in this case (it's reporting, not failing), so
without this check the workflow can't tell "gave up and commented" from
"finished the fix" and would re-run the reviewer.

Emits gave_up=true|false on $GITHUB_OUTPUT so the workflow skips the
reviewer hand-off when the task was declined.
"""

from __future__ import annotations

import os

from .. import cli
from ..ctx import ActionsCtx
from ..domain import lifecycle, lifecycle_apply
from ..env_spec import EnvSpec

ENV_SPEC = EnvSpec.of("GITHUB_OUTPUT", "GITHUB_RUN_ID", "GITHUB_WORKSPACE")

SENTINEL_NAME = ".coder-gave-up.md"


def handle_giveup(repo: str, issue: int, pr: int | None, workspace: str, *, run_url: str = "") -> bool:
    sentinel = os.path.join(workspace, SENTINEL_NAME)
    if not os.path.isfile(sentinel):
        cli.write_output("gave_up", False)
        return False

    with open(sentinel) as f:
        reason = f.read().strip() or "_(no reason given)_"

    outcome = lifecycle.decide(lifecycle.Event.CODER_GAVE_UP, lifecycle.Facts(has_issue=True, has_pr=pr is not None))
    lifecycle_apply.apply(repo, outcome, pr=pr, issue=issue, words=lifecycle_apply.Words(run_url=run_url, detail=reason))
    cli.write_output("gave_up", True)
    return True


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("handle-giveup")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--pr", default="")
    args = parser.parse_args(argv)

    cli.require_env("GITHUB_OUTPUT")  # fail before the give-up side effects, not after
    handle_giveup(
        ctx.repo,
        args.issue,
        cli.optional_int(args.pr),
        ctx.workspace,
        run_url=ctx.run_url(),
    )
    return 0
