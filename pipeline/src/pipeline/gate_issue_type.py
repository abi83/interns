"""Deterministic issue-type gate, shared by the estimate and code jobs. An
issue whose type:* label isn't in the accepted list never reaches an agent:
post a comment, park the issue on status:needs-attention, and tell the
calling job to skip its Claude step. Running a full agent invocation just to
execute a fixed check on a label already present when the job starts is
wasteful and fragile.

Invoked by the gate-issue-type composite action.
"""

from __future__ import annotations

import sys

from . import gh, labels


def gate(repo: str, issue: int, accepted: list[str], remove_status: str, reject_comment: str) -> bool:
    """True when the issue's type is accepted and the caller should proceed.
    False after parking the issue on status:needs-attention and commenting
    the rejection."""
    current = labels.issue_labels(repo, issue)
    if any(label in current for label in accepted):
        return True
    labels.edit_issue_labels(repo, issue, add=["status:needs-attention"], remove=[remove_status])
    gh.issue_comment(repo, issue, reject_comment)
    return False


def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="python -m pipeline.gate_issue_type")
    parser.add_argument("issue", type=int)
    parser.add_argument("accepted", help="comma-separated type:* labels the calling job can handle")
    parser.add_argument("remove_status")
    parser.add_argument("reject_comment")
    args = parser.parse_args(argv)

    accepted = [label for label in args.accepted.split(",") if label]
    ok = gate(os.environ["GITHUB_REPOSITORY"], args.issue, accepted, args.remove_status, args.reject_comment)
    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
        f.write(f"skip={'false' if ok else 'true'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
