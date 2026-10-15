"""Runs after a coder fix round. A ./.coder-gave-up.md sentinel means the agent
*declined* the task (needs a protected path, out of scope, or an owner decision):
escalate to a human instead of wasting a reviewer round.

The coder step still exits 0 then, so the workflow can't tell "gave up" from
"finished the fix" without this check. Emits gave_up=true|false on $GITHUB_OUTPUT.
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
