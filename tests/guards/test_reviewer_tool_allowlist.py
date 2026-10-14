"""The reviewer's Bash allowlist is read-only; its `gh` calls run as the reviewer App."""

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/code-pipeline.yml"
READ_ONLY_COMMANDS = {
    "git diff",
    "git log",
    "git show",
    "git status",
    "gh pr diff",
    "gh pr view",
    "gh pr checks",
    "gh run view",
}
REVIEWER_STEP = "Run Claude reviewer"


def step(name: str) -> str:
    blocks = re.split(r"(?m)^      - name: ", WORKFLOW.read_text())
    (match,) = [b for b in blocks if b.startswith(f"{name}\n")]
    return match


def env_value(name: str) -> str:
    match = re.search(rf'^\s+{name}: "(.*)"$', WORKFLOW.read_text(), re.MULTILINE)
    assert match, name
    return match.group(1)


def bash_commands(allowed_tools: str) -> set[str]:
    expanded = re.sub(r"\$\{\{ env\.(\w+) \}\}", lambda m: env_value(m.group(1)), allowed_tools)
    return set(re.findall(r"Bash\((.+?):\*\)", expanded))


def allowed_tools() -> str:
    match = re.search(r"AGENT_ALLOWED_TOOLS: (.*)", step(REVIEWER_STEP))
    assert match
    return match.group(1)


def test_allowlist_is_read_only():
    assert bash_commands(allowed_tools()) == READ_ONLY_COMMANDS


def test_pins_builtin_tools_and_appends_consumer_additions():
    block = step(REVIEWER_STEP)
    assert "AGENT_TOOLS: Read,Grep,Glob,Bash${{ steps.cfg.outputs.tools_suffix }}" in block
    assert allowed_tools().endswith("${{ steps.cfg.outputs.allowed_tools_suffix }}")
    assert "AGENT_DISALLOWED_TOOLS: ${{ steps.cfg.outputs.disallowed_tools }}" in block


def test_runs_gh_as_the_reviewer_app():
    assert "GH_TOKEN: ${{ steps.reviewer_token.outputs.token }}" in step(REVIEWER_STEP)
