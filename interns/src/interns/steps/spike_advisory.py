"""Posts the spike advisory on a `type:spike` issue after estimation. The
estimate is the end of a spike's pipeline path -- no coder picks it up -- so
the owner needs that spelled out. The notice comes from the workflow, not
the agent: type:spike is known from the issue's labels before the agent
runs, so there's nothing for the agent to decide.

No-op on any other issue type, or a spike not yet estimated.
"""

from __future__ import annotations

from .. import cli, gh
from ..domain import labels
from ..ctx import ActionsCtx
from ..env_spec import EnvSpec

ENV_SPEC = EnvSpec.of()

ADVISORY = (
    "This is a spike; no coder picks it up. The estimate above is for your "
    "planning — do the investigation and close the issue when done."
)


def post_advisory(repo: str, issue: int) -> str | None:
    """Posts the advisory and returns it, or None (and posts nothing) when
    the issue isn't an estimated spike."""
    current = set(labels.issue_labels(repo, issue))
    if labels.TYPE_SPIKE not in current:
        return None
    if labels.STATUS_ESTIMATED not in current:
        return None
    gh.issue_comment(repo, issue, ADVISORY)
    return ADVISORY


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("spike-advisory")
    parser.add_argument("--issue", type=int, required=True)
    args = parser.parse_args(argv)

    if post_advisory(ctx.repo, args.issue) is None:
        print(f"Issue #{args.issue} is not an estimated spike — no advisory.")
    return 0
