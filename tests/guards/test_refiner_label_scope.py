"""The refiner reads untrusted issue text and runs on the triage token (whose label events fire workflows).

Its only label writes are `set_issue_type` (type:* only) and the outcome tool, so it
can't add status:ready and skip the owner's approval gate.
"""

import inspect
import re
import typing
from pathlib import Path

import server

ISSUE_PIPELINE = (Path(__file__).resolve().parents[2] / ".github/workflows/issue-pipeline.yml").read_text()
REFINER_TOOLS = {"list_issues", "view_issue", "set_issue_type", "edit_issue", "comment_issue", "apply_refinement_outcome"}


def refiner_tools() -> set[str]:
    refine_job = ISSUE_PIPELINE.split("\n  estimate:")[0]
    match = re.search(r"^\s+tools: (\S+)$", refine_job, re.MULTILINE)
    assert match, "refine job has no gh-issues `tools:` input"
    return set(match.group(1).split(","))


def refine_job() -> str:
    return ISSUE_PIPELINE.split("\n  estimate:")[0]


def test_refiner_tool_set_is_exactly_the_reviewed_one():
    assert refiner_tools() == REFINER_TOOLS


def test_no_tool_accepts_free_form_label_names():
    """Only `list_issues` takes a label, to filter by; nothing writes an arbitrary one."""
    offenders = []
    for name, fn in server._TOOLS.items():
        for param, hint in typing.get_type_hints(fn).items():
            closed = hint in (server.labels.TypeLabel, server.labels.TypeLabel | None)
            if "label" in param and name != "list_issues" and not closed:
                offenders.append(f"{name}.{param}")
    assert not offenders, f"label parameters must be closed sets (TypeLabel): {offenders}"


def test_set_issue_type_parameter_is_the_shared_type_label_set():
    hints = typing.get_type_hints(server.set_issue_type)
    assert hints["type_label"] is server.labels.TypeLabel
    assert list(inspect.signature(server.set_issue_type).parameters) == ["issue_number", "type_label"]
