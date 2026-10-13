"""claude-code-action refuses a bot-triggered run unless that bot is in allowed_bots,
so each agent step must allowlist the identity that triggers it."""

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"

TRIAGE = "${{ steps.triage_ident.outputs.bot }}"
CODER = "${{ needs.plan.outputs.coder_bot }}"

TRIGGERING_BOTS: dict[tuple[str, str], list[str]] = {
    ("issue-pipeline.yml", "Run Claude refinement"): [],
    ("issue-pipeline.yml", "Run Claude estimation"): [TRIAGE],
    ("code-pipeline.yml", "Run Claude coder (initial implementation)"): [TRIAGE],
    ("code-pipeline.yml", "Run Claude coder (fix round)"): ["github-actions[bot]"],
    ("code-pipeline.yml", "Run Claude reviewer"): [CODER],
}


def claude_steps() -> dict[tuple[str, str], str]:
    steps = {}
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for block in re.split(r"(?m)^      - name: ", path.read_text())[1:]:
            if "uses: anthropics/claude-code-action" in block:
                steps[(path.name, block.split("\n", 1)[0])] = block
    return steps


def allowed_bots(block: str) -> list[str]:
    match = re.search(r'allowed_bots: "([^"]*)"', block)
    assert match, "claude-code-action step has no allowed_bots"
    return match.group(1).split(",")


def test_every_claude_step_declares_its_triggering_bots():
    assert set(claude_steps()) == set(TRIGGERING_BOTS)


def test_each_claude_step_allowlists_the_bots_that_trigger_it():
    for key, block in claude_steps().items():
        missing = [bot for bot in TRIGGERING_BOTS[key] if bot not in allowed_bots(block)]
        assert not missing, f"{key} must allow {missing}"


def test_triage_and_coder_identities_are_resolved_before_their_use():
    code = (WORKFLOWS / "code-pipeline.yml").read_text()
    assert code.index("id: triage_ident") < code.index("name: Run Claude coder (initial implementation)")
    assert code.index("coder_bot: ${{ steps.coder_token.outputs.app-slug }}[bot]") < code.index("name: Run Claude reviewer")
