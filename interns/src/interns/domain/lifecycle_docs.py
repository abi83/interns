"""Renders the PR-loop lifecycle section of docs/architecture.md from `lifecycle.SCENARIOS`,
so the documented transitions cannot drift from `lifecycle.decide`.

Regenerate with `PYTHONPATH=interns/src uv run --frozen python -m interns.domain.lifecycle_docs`.
"""

from __future__ import annotations

from pathlib import Path

from . import labels
from .lifecycle import SCENARIOS, IssueChange, Outcome, Scenario, decide

START = "<!-- lifecycle:start -->"
END = "<!-- lifecycle:end -->"

DOC = Path(__file__).resolve().parents[4] / "docs" / "architecture.md"

_ISSUE_TEXT = {
    IssueChange.UNCHANGED: "unchanged",
    IssueChange.NEEDS_ATTENTION: f"`{labels.STATUS_NEEDS_ATTENTION}`",
    IssueChange.RETIRE_IN_PROGRESS: f"drops `{labels.STATUS_IN_PROGRESS}`",
}


def _pr_text(outcome: Outcome) -> str:
    return f"`{outcome.pr_label}`" if outcome.pr_label else "none"


def _comment_text(outcome: Outcome) -> str:
    return f"{outcome.comment.kind} on the {outcome.comment.target}" if outcome.comment else "none"


def _dispatch_text(outcome: Outcome) -> str:
    return "coder fix round" if outcome.dispatch_fix_round else "none"


def _table(rows: list[tuple[Scenario, Outcome]]) -> str:
    lines = [
        "| Event | Situation | PR label | Issue | Comment | Dispatch |",
        "|---|---|---|---|---|---|",
    ]
    for scenario, outcome in rows:
        cells = (
            f"`{scenario.event}`",
            scenario.name,
            _pr_text(outcome),
            _ISSUE_TEXT[outcome.issue],
            _comment_text(outcome),
            _dispatch_text(outcome),
        )
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render() -> str:
    rows = [(scenario, decide(scenario.event, scenario.facts)) for scenario in SCENARIOS]
    return f"{START}\n{_table(rows)}\n{END}"


def splice(doc: str) -> str:
    start, end = doc.index(START), doc.index(END) + len(END)
    return doc[:start] + render() + doc[end:]


if __name__ == "__main__":
    DOC.write_text(splice(DOC.read_text()))
