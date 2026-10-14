"""Every `claude -p` the launcher starts runs with `--permission-mode default`: a fresh CLI can
otherwise start in `auto` mode and run non-allowlisted tools without a denial. The argv is built
in one place, hard-coded there, and nothing else spawns the CLI or lowers the guard."""

import ast
from pathlib import Path

from interns.domain import agent_run
from interns.domain.agent_run import AgentRun

PACKAGE = Path(__file__).resolve().parents[2] / "interns/src/interns"
BUILDER = PACKAGE / "domain/agent_run.py"
BYPASS_FLAGS = ("--dangerously-skip-permissions", "bypassPermissions", "acceptEdits")


def spawns_claude(source: str) -> bool:
    return any(isinstance(n, ast.Constant) and n.value == "claude" for n in ast.walk(ast.parse(source)))


def permission_mode_values(source: str) -> list[object]:
    """Constants following a "--permission-mode" element in any list literal."""
    values: list[object] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.List):
            continue
        for flag, value in zip(node.elts, node.elts[1:], strict=False):
            if isinstance(flag, ast.Constant) and flag.value == "--permission-mode":
                values.append(getattr(value, "value", None))
    return values


def test_detects_a_claude_argv():
    assert spawns_claude('subprocess.run(["claude", "-p"])')
    assert permission_mode_values('["--permission-mode", "auto"]') == ["auto"]


def test_only_the_launcher_builder_names_the_claude_binary():
    offenders = [str(p) for p in PACKAGE.rglob("*.py") if p != BUILDER and spawns_claude(p.read_text())]
    assert not offenders, f"build the claude argv in domain/agent_run.py only: {offenders}"


def test_the_builder_hardcodes_permission_mode_default():
    assert permission_mode_values(BUILDER.read_text()) == ["default"]


def test_the_builder_never_names_a_permission_bypass():
    text = BUILDER.read_text()
    assert not [flag for flag in BYPASS_FLAGS if flag in text]


def test_every_built_command_carries_permission_mode_default():
    variants = [
        dict(),
        dict(disallowed_tools=["Write"]),
        dict(add_dirs=["/w", "/v"]),
        dict(allowed_tools="", tools=""),
    ]
    for overrides in variants:
        fields = dict(model="m", max_turns=1, mcp_config="c", tools="Read", allowed_tools="Read",
                      disallowed_tools=[], add_dirs=[], debug_file="d")
        command = agent_run.build_command(AgentRun(**{**fields, **overrides}))
        assert command.count("--permission-mode") == 1
        assert command[command.index("--permission-mode") + 1] == "default"
