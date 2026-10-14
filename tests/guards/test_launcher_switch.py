"""A phase runs through exactly one of claude-code-action and the launcher, chosen by its
`launcher` config key: the two steps carry complementary conditions in the same job."""

import re
from pathlib import Path

WORKFLOWS = sorted((Path(__file__).resolve().parents[2] / ".github/workflows").glob("*.yml"))
LAUNCHER_ON = "if: steps.cfg.outputs.launcher == 'true'"
LAUNCHER_OFF = "if: steps.cfg.outputs.launcher != 'true'"


def jobs(text: str) -> list[str]:
    return re.split(r"(?m)^  (?=[a-z_-]+:\n)", text.split("\njobs:\n", 1)[1])


def steps(job: str) -> list[str]:
    return re.split(r"(?m)^      - name: ", job)[1:]


def test_launcher_steps_have_a_switched_off_action_counterpart():
    seen = 0
    for wf in WORKFLOWS:
        for job in jobs(wf.read_text()):
            action_steps = [s for s in steps(job) if "uses: anthropics/claude-code-action" in s]
            for step in (s for s in steps(job) if "interns.entrypoint run-agent" in s):
                seen += 1
                assert LAUNCHER_ON in step, step
                assert action_steps and all(LAUNCHER_OFF in a for a in action_steps), job[:80]
                assert "uses: ./.interns/.github/actions/install-claude-cli" in job
                assert "uses: ./.interns/.github/actions/agent-result" in job
    assert seen >= 1
