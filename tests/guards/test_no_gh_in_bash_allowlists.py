"""Agents reach GitHub only through the gh-issues MCP server, never `gh` in Bash."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALLOWLISTS = [*sorted((ROOT / ".github/workflows").glob("*.yml")), ROOT / "templates/config/defaults.yml"]


def test_default_allowlists_exist():
    assert all(path.is_file() for path in DEFAULT_ALLOWLISTS)


def test_no_default_allowlist_permits_gh_in_bash():
    offenders = [path.name for path in DEFAULT_ALLOWLISTS if "Bash(gh" in path.read_text()]
    assert not offenders, f"Bash(gh ...) in default allowlists: {offenders}"
