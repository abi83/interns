"""Parsing of the claude-code-action execution-log JSON.

Shared by pipeline.report_run and pipeline.run_summary, which both
previously hand-duplicated the same `result`-entry extraction (interns#157).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import best_effort, cli


def events(exec_file: str) -> list[dict]:
    """Parse an execution log file into the event list. Raises
    json.JSONDecodeError on an invalid or truncated file; callers that treat
    this as a soft failure should catch it themselves."""
    return json.loads(Path(exec_file).read_text())


def result_entry(exec_file: str | None) -> dict | None:
    """The log's result-type entry, or None when the file is missing, not
    valid JSON, or has no result entry."""
    if not exec_file:
        return None
    path = Path(exec_file)
    if not path.is_file():
        return None
    entries = best_effort.call("exec log parse", json.JSONDecodeError, json.loads, path.read_text())
    if entries is None:
        return None
    for entry in entries:
        if entry.get("type") == "result":
            return entry
    return None


def result_field(exec_file: str | None, field: str) -> str | None:
    """Value of `field` on the log's `result`-type entry -- the one written
    when the agent run finished normally. None when there is no execution
    file (a timed-out run is SIGKILLed before writing one), the file isn't
    valid JSON (a partial write under disk pressure), or there's no result
    entry -- every caller treats "we have no reliable data" the same way,
    regardless of which of these produced it."""
    entry = result_entry(exec_file)
    if entry is None:
        return None
    value = entry.get(field)
    return str(value) if value not in (None, "") else None


def _main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pipeline.execution")
    parser.add_argument("exec_file")
    parser.add_argument("field")
    args = parser.parse_args(argv)
    print(result_field(args.exec_file, args.field) or "")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(_main))
