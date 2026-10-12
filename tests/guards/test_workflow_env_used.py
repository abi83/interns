"""Every workflow-level `env:` variable is referenced somewhere in its workflow."""

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parents[2] / ".github/workflows").glob("*.yml"))


def workflow_env_names(text: str) -> list[str]:
    block = re.search(r"^env:\n((?:(?:  .*)?\n)+)", text, re.MULTILINE)
    if not block:
        return []
    return re.findall(r"^  ([A-Z][A-Z0-9_]*):", block.group(1), re.MULTILINE)


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_level_env_vars_are_referenced(path: Path):
    text = path.read_text()
    unused = [n for n in workflow_env_names(text) if len(re.findall(rf"\b{n}\b", text)) < 2]
    assert not unused, f"{path.name}: defined but never referenced: {unused}"


def test_guard_detects_an_unreferenced_variable():
    text = "env:\n  USED: a\n  DEAD: b\njobs:\n  x: ${{ env.USED }}\n"
    assert workflow_env_names(text) == ["USED", "DEAD"]
