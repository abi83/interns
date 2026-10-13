"""Environment variables are read through cli.require_env. A raw
`os.environ.get(..., "")` / `os.environ[...]` elsewhere either hides a missing
value behind a default or raises a bare KeyError.
"""

import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "interns/src/interns"
OPTIONAL_VARS = {"INTERNS_CONFIG"}
EMPTY_BODY_VARS = {"ISSUE_BODY"}  # an empty issue body is valid, so require_env's non-empty rule doesn't fit
ALLOWED = OPTIONAL_VARS | EMPTY_BODY_VARS

RAW_ACCESS = re.compile(r"""os\.(?:environ\.get\(|environ\[|getenv\()\s*["'](\w+)["']""")


def raw_env_reads(source: str) -> set[str]:
    return set(RAW_ACCESS.findall(source))


def test_detects_raw_reads():
    source = 'a = os.environ.get("A", "")\nb = os.environ["B"]\nc = os.getenv("C")\n'
    assert raw_env_reads(source) == {"A", "B", "C"}


def test_only_allowlisted_vars_are_read_outside_cli():
    offenders = {
        f"{path.relative_to(PACKAGE)}: {name}"
        for path in PACKAGE.rglob("*.py")
        if path.name != "cli.py"
        for name in raw_env_reads(path.read_text()) - ALLOWED
    }
    assert not offenders, f"read via cli.require_env instead: {sorted(offenders)}"
