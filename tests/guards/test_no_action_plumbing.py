"""Agents run through the launcher only: no workflow or consumer template may reintroduce the
third-party action or the OIDC permission it needed."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = [*(ROOT / ".github/workflows").glob("*.yml"), *(ROOT / "templates/workflows").glob("*.yml")]
FORBIDDEN = ("claude-code-" + "action", "id-" + "token", "allowed_" + "bots")


def test_no_workflow_or_template_uses_the_removed_plumbing():
    offenders = [f"{f.relative_to(ROOT)}: {word}" for f in FILES for word in FORBIDDEN if word in f.read_text()]
    assert not offenders, offenders
