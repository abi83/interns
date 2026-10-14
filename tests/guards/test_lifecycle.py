"""The PR-loop label lifecycle is defined once, in `interns.domain.lifecycle`."""

import ast
from pathlib import Path

from interns.domain import lifecycle_docs

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "interns/src/interns"
LIFECYCLE_WRITES = {"set_pr_pipeline_label", "set_issue_status", "escalate_pr"}
# The `labels` command is the workflow shells' direct label interface, not a lifecycle decision.
DIRECT_WRITERS = {"edit_labels.py"}


def called_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Call):
            func = node.func
            names.add(func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", ""))
    return names


def imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_steps_never_write_lifecycle_labels_directly():
    offenders = {
        path.name: sorted(called_names(path) & LIFECYCLE_WRITES)
        for path in sorted((PACKAGE / "steps").glob("*.py"))
        if path.name not in DIRECT_WRITERS and called_names(path) & LIFECYCLE_WRITES
    }
    assert not offenders, f"route label moves through lifecycle.decide / lifecycle_apply.apply: {offenders}"


def test_decide_module_does_no_io():
    modules = imported_modules(PACKAGE / "domain/lifecycle.py")
    assert not {"gh", "subprocess", "os", "requests"} & modules, modules


def test_architecture_lifecycle_section_matches_the_definitions():
    doc = (ROOT / "docs" / "architecture.md").read_text()
    assert lifecycle_docs.splice(doc) == doc, (
        "architecture.md lifecycle section is stale; run "
        "`PYTHONPATH=interns/src uv run --frozen python -m interns.domain.lifecycle_docs`"
    )
