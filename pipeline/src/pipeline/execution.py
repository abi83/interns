"""Parsing of the claude-code-action execution-log JSON.

Shared by report-run.sh and run-summary.sh, which both previously
hand-duplicated the same `result`-entry extraction (interns#157).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def result_field(exec_file: str | None, field: str) -> str | None:
    """Value of `field` on the log's `result`-type entry -- the one written
    when the agent run finished normally. None when there is no execution
    file (a timed-out run is SIGKILLed before writing one) or no result
    entry."""
    if not exec_file:
        return None
    path = Path(exec_file)
    if not path.is_file():
        return None
    entries = json.loads(path.read_text())
    for entry in entries:
        if entry.get("type") == "result":
            value = entry.get(field)
            return str(value) if value not in (None, "") else None
    return None


def _main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pipeline.execution")
    parser.add_argument("exec_file")
    parser.add_argument("field")
    args = parser.parse_args(argv)
    print(result_field(args.exec_file, args.field) or "")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
