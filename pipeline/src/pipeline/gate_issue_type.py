"""Deterministic issue-type gate, shared by the estimate and code jobs. An
issue whose type:* label isn't in the accepted list never reaches an agent:
post a comment, park the issue on status:needs-attention, and tell the
calling job to skip its Claude step. Running a full agent invocation just to
execute a fixed check on a label already present when the job starts is
wasteful and fragile.

Invoked by the gate-issue-type composite action.
"""

from __future__ import annotations

from . import cli, gh, labels
from .ctx import ActionsCtx


def gate(repo: str, issue: int, accepted: list[str], remove_status: str, reject_comment: str) -> bool:
    """True when the issue's type is accepted and the caller should proceed.
    False after parking the issue on status:needs-attention and commenting
    the rejection."""
    current = labels.issue_labels(repo, issue)
    if any(label in current for label in accepted):
        return True
    labels.edit_issue_labels(repo, issue, add=[labels.STATUS_NEEDS_ATTENTION], remove=[remove_status])
    gh.issue_comment(repo, issue, reject_comment)
    return False


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="pipeline.entrypoint gate-issue-type")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--accepted", required=True,
                        help="comma-separated type:* labels the calling job can handle")
    parser.add_argument("--remove-status", required=True)
    parser.add_argument("--reject-comment", required=True)
    args = parser.parse_args(argv)

    accepted = [label for label in args.accepted.split(",") if label]
    ok = gate(ctx.repo, args.issue, accepted, args.remove_status, args.reject_comment)
    cli.write_output("skip", not ok)
    return 0
