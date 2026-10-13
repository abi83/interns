"""`plan-coder-run`: decides whether the coder job runs and whether it is a fix round.

A fix round is dispatched explicitly by the reviewer against an issue that is
already `status:in-progress`, so it bypasses the type gate and the stale-trigger
check. An initial run is skipped when the issue's type isn't implementable or it
has already moved past `status:ready`.
"""

from __future__ import annotations

from .. import cli
from ..ctx import ActionsCtx
from ..domain import labels, plan, type_gate

ACCEPTED_TYPES = [labels.TYPE_CODING_TASK, labels.TYPE_BUG]
REJECT_COMMENT = (
    "This issue reached `status:ready` without a `type:coding-task` or "
    "`type:bug` label, so the coder agent won't attempt it — only those "
    "two types are implementable code deliverables. If this should be "
    "implemented, add the correct type label and re-apply `status:ready`."
)


def should_skip(repo: str, issue: int, *, fix_round: bool) -> bool:
    if fix_round:
        return False
    if not type_gate.gate(repo, issue, ACCEPTED_TYPES, labels.STATUS_READY, REJECT_COMMENT):
        return True
    current = labels.issue_labels(repo, issue)
    if plan.is_stale_trigger(current):
        print(f"Issue #{issue} is already past status:ready ({', '.join(current)}) — stale or duplicate trigger, skipping.")
        return True
    return False


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("plan-coder-run")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--fix-round", choices=["true", "false"], required=True)
    args = parser.parse_args(argv)

    fix_round = args.fix_round == "true"
    cli.write_output("skip", should_skip(ctx.repo, args.issue, fix_round=fix_round))
    cli.write_output("fix_round", fix_round)
    return 0
