"""Deterministic issue-type gate, shared by the estimate and code jobs. An
issue whose type:* label isn't in the accepted list never reaches an agent:
post a comment, park the issue on status:needs-attention, and tell the
caller to skip the agent run. Running a full agent invocation just to
execute a fixed check on a label already present when the job starts is
wasteful and fragile.

Invoked by the plan steps.
"""

from __future__ import annotations

from .. import gh
from . import labels


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
