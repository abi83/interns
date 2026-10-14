"""Every agent phase pins its built-in tool ceiling (`--tools`) and appends the consumer's additions and denials."""

import re
from pathlib import Path

WORKFLOWS = sorted((Path(__file__).resolve().parents[2] / ".github/workflows").glob("*.yml"))
PHASE_COUNT = 5  # refiner, estimator, coder initial, coder fix, reviewer


def env_blocks() -> list[str]:
    return [
        block
        for wf in WORKFLOWS
        for block in re.findall(r"(?m)^          AGENT_TOOLS: .*\n(?:          AGENT_.*\n)+", wf.read_text())
    ]


def test_every_phase_pins_builtin_tools_and_appends_consumer_additions():
    blocks = env_blocks()
    assert len(blocks) == PHASE_COUNT
    for block in blocks:
        assert re.search(r"AGENT_TOOLS: [^\n]*\$\{\{ steps\.cfg\.outputs\.tools_suffix \}\}\n", block), block
        assert re.search(r"AGENT_ALLOWED_TOOLS: [^\n]*\$\{\{ steps\.cfg\.outputs\.allowed_tools_suffix \}\}\n", block), block
        assert "AGENT_DISALLOWED_TOOLS: ${{ steps.cfg.outputs.disallowed_tools }}\n" in block, block
        assert "AGENT_ADD_DIR: ${{ steps.cfg.outputs.wiki_dir }}\n" in block, block
