"""Docs and code must not point at the removed `pipeline` package or at files that do not exist."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
STALE_MODULE = re.compile(r"\bpipeline\.[a-z_]+|python -m pipeline|pipeline/src")
WORKFLOW_FILE_NAME = re.compile(r"(?:[a-z}]-)?pipeline\.yml")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
EXTERNAL = ("http://", "https://", "mailto:", "#")


def _tracked_files(*suffixes: str) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [ROOT / name for name in out.split("\0") if name.endswith(suffixes) and (ROOT / name).is_file()]


def test_no_stale_pipeline_module_names():
    offenders = []
    for path in _tracked_files(".py", ".yml", ".yaml", ".json", ".md", ".sh"):
        if path == THIS_FILE:
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if STALE_MODULE.search(WORKFLOW_FILE_NAME.sub("", line)):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    assert not offenders, "stale `pipeline.*` references:\n" + "\n".join(offenders)


def test_relative_markdown_links_resolve():
    broken = []
    for path in _tracked_files(".md"):
        text = FENCE.sub("", path.read_text())
        for target in MARKDOWN_LINK.findall(text):
            if target.startswith(EXTERNAL):
                continue
            if not (path.parent / target.split("#")[0]).exists():
                broken.append(f"{path.relative_to(ROOT)}: {target}")
    assert not broken, "broken relative links:\n" + "\n".join(broken)
