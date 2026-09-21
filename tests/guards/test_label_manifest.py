"""`.github/labels.json` and the label constants in `pipeline.labels`/`pipeline.size` must agree."""

import json
import re
from pathlib import Path

from pipeline import labels, size

MANIFEST = Path(__file__).resolve().parents[2] / ".github/labels.json"
LIFECYCLE_PREFIXES = ("status:", "pr:")


def manifest_names() -> set[str]:
    return {entry["name"] for entry in json.loads(MANIFEST.read_text())["labels"]}


def code_labels() -> set[str]:
    return {
        value for name, value in vars(labels).items()
        if name.isupper() and isinstance(value, str) and re.match(r"^(status|pr|type):", value)
    }


def test_every_label_constant_is_in_the_manifest():
    assert code_labels() - manifest_names() == set()


def test_every_lifecycle_label_in_the_manifest_has_a_constant():
    lifecycle = {name for name in manifest_names() if name.startswith(LIFECYCLE_PREFIXES)}
    assert lifecycle - code_labels() == set()


def test_size_labels_match_the_roll_up_table():
    in_manifest = {name for name in manifest_names() if name.startswith(labels.SIZE_PREFIX)}
    from_table = {labels.size_label(value) for value in size._ROLL_UP_TABLE.values()}
    assert in_manifest == from_table
