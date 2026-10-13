"""Pure skip/run predicates behind the `plan` job's decisions."""

from __future__ import annotations

from collections.abc import Sequence

from . import labels

STALE_TRIGGER_STATUSES = (labels.STATUS_IN_PROGRESS, labels.STATUS_NEEDS_ATTENTION)


def is_stale_trigger(issue_labels: Sequence[str]) -> bool:
    """An initial coder run is only valid while the issue is still `status:ready`."""
    return any(status in issue_labels for status in STALE_TRIGGER_STATUSES)


def is_foreign_bot(author_login: str, author_type: str, coder_bot: str) -> bool:
    """A bot-authored PR that isn't the coder's own App (Dependabot, etc.) is not a pipeline PR."""
    return author_type == "Bot" and author_login != coder_bot
