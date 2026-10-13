"""`plan-estimate-run`: decides whether the estimate job runs.

The refiner can no longer produce a type:epic, so on the happy path the
estimator never sees one; this catches a manual mislabel or a workflow_dispatch
with a pure label transition, no agent.
"""

from __future__ import annotations

from .. import cli
from ..ctx import ActionsCtx
from ..domain import labels, type_gate

ACCEPTED_TYPES = [labels.TYPE_CODING_TASK, labels.TYPE_BUG, labels.TYPE_SPIKE]
REJECT_COMMENT = (
    "Epics aren't sized directly — a dev-effort number doesn't mean "
    "anything before the work is broken down. Break this into sub-issues "
    "and estimate those."
)


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("plan-estimate-run")
    parser.add_argument("--issue", type=int, required=True)
    args = parser.parse_args(argv)

    accepted = type_gate.gate(ctx.repo, args.issue, ACCEPTED_TYPES, labels.STATUS_REFINED, REJECT_COMMENT)
    cli.write_output("skip", not accepted)
    return 0
