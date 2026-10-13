"""Every lifecycle label a workflow names (triggers, `if:` conditions, shell steps) exists in the manifest."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".github/labels.json"
WORKFLOW_DIRS = (ROOT / ".github/workflows", ROOT / "templates/workflows", ROOT / ".github/actions")
LABEL_REF = re.compile(r"(?<![\w./-])(?:status|pr|type|size):[A-Za-z][\w-]*")


def manifest_names() -> set[str]:
    return {entry["name"] for entry in json.loads(MANIFEST.read_text())["labels"]}


def workflow_files() -> list[Path]:
    files = sorted(p for d in WORKFLOW_DIRS for p in d.rglob("*.yml"))
    assert files
    return files


def test_detects_a_label_reference():
    assert LABEL_REF.findall("if: github.event.label.name == 'status:ready'") == ["status:ready"]


def test_every_workflow_label_reference_is_in_the_manifest():
    known = manifest_names()
    unknown = {
        f"{path.relative_to(ROOT)}: {ref}"
        for path in workflow_files()
        for ref in LABEL_REF.findall(path.read_text())
        if ref not in known
    }
    assert not unknown, f"labels referenced in workflows but missing from .github/labels.json: {sorted(unknown)}"
