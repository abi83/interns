"""Every agent phase pins its built-in tool ceiling (`--tools`) and appends the consumer's additions and denials."""

import re
from pathlib import Path

WORKFLOWS = sorted((Path(__file__).resolve().parents[2] / ".github/workflows").glob("*.yml"))
PHASE_COUNT = 5  # refiner, estimator, coder initial, coder fix, reviewer


def claude_args_blocks() -> list[str]:
    return [block for wf in WORKFLOWS for block in re.findall(r"claude_args: \|\n((?:\s{12}.*\n)+)", wf.read_text())]


def test_every_phase_is_covered():
    assert len(claude_args_blocks()) == PHASE_COUNT


def test_every_phase_pins_builtin_tools_and_appends_consumer_additions():
    for block in claude_args_blocks():
        assert re.search(r'--tools "[^"]*\$\{\{ steps\.cfg\.outputs\.tools_suffix \}\}"', block), block
        assert re.search(r'--allowedTools "[^"]*\$\{\{ steps\.cfg\.outputs\.allowed_tools_suffix \}\}"', block), block
        assert "${{ steps.cfg.outputs.disallowed_tools_arg }}" in block, block


def test_no_phase_hardcodes_a_denylist():
    for block in claude_args_blocks():
        assert "--disallowedTools" not in block, block
