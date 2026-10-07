"""Each phase's exposed gh-issues tools (`tools:` input) must match its `--allowedTools` MCP entries.

Exposed but not allowed: the model sees a tool headless mode will deny.
Allowed but not exposed: the allowlist entry is dead and the model can't call it.
"""

import re
from pathlib import Path

import server

WORKFLOWS = sorted((Path(__file__).resolve().parents[2] / ".github/workflows").glob("*.yml"))
SETUP_ACTION = "./.interns/.github/actions/setup-gh-issues-mcp"
MCP_PREFIX = "mcp__gh-issues__"


def allowed_env(text: str) -> dict[str, str]:
    return dict(re.findall(r'^\s+(ALLOWED_\w+): "' + MCP_PREFIX + r'(\w+)"$', text, re.MULTILINE))


def phases(text: str) -> list[tuple[set[str], set[str]]]:
    """(exposed, allowed) per setup step; allowed spans every --allowedTools line up to the next setup step."""
    env = allowed_env(text)
    result = []
    for chunk in text.split(f"uses: {SETUP_ACTION}")[1:]:
        tools_line = re.search(r"^\s+tools: (\S+)$", chunk, re.MULTILINE)
        assert tools_line, "setup-gh-issues-mcp step without a `tools:` input"
        exposed = set(tools_line.group(1).split(","))
        refs = re.findall(r"--allowedTools \"(.*)\"", chunk)
        allowed = {env[name] for line in refs for name in re.findall(r"env\.(ALLOWED_\w+)", line) if name in env}
        result.append((exposed, allowed))
    return result


def all_phases() -> list[tuple[str, set[str], set[str]]]:
    return [(wf.name, exposed, allowed) for wf in WORKFLOWS for exposed, allowed in phases(wf.read_text())]


def test_every_setup_step_is_covered():
    assert len(all_phases()) == 4


def test_exposed_tools_match_allowed_tools_per_phase():
    for workflow, exposed, allowed in all_phases():
        assert exposed == allowed, f"{workflow}: exposed {sorted(exposed)} != allowed {sorted(allowed)}"


def test_exposed_tools_exist_on_the_server():
    for workflow, exposed, _ in all_phases():
        assert exposed <= server._TOOLS.keys(), f"{workflow}: unknown {sorted(exposed - server._TOOLS.keys())}"
