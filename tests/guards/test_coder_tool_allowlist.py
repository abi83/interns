"""The coder's Bash allowlist may grow read-only filesystem commands, never a write path."""

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github/workflows/code-pipeline.yml"
READ_ONLY_COMMANDS = {"ls", "cat", "find", "head", "wc"}
WRITE_CAPABLE = {"sed", "awk", "tee", "rm", "mv", "cp", "chmod", "dd", "xargs", "perl", "python", "python3"}


def env_value(name: str) -> str:
    match = re.search(rf'^\s+{name}: "(.*)"$', WORKFLOW.read_text(), re.MULTILINE)
    assert match, f"{name} not found in {WORKFLOW.name}"
    return match.group(1)


def bash_commands(patterns: str) -> set[str]:
    return set(re.findall(r"Bash\((\S+?):\*\)", patterns))


def coder_allowed_tools() -> list[str]:
    lines = re.findall(r"--allowedTools \"(.*)\"", WORKFLOW.read_text())
    return [line for line in lines if "Write,Edit" in line]


def test_fs_read_allowlist_is_exactly_the_read_only_commands():
    assert bash_commands(env_value("ALLOWED_FS_READ")) == READ_ONLY_COMMANDS


def test_no_write_capable_command_is_allowed_for_the_coder():
    for line in coder_allowed_tools():
        assert bash_commands(line) & WRITE_CAPABLE == set()


def test_initial_and_fix_round_both_get_fs_read():
    lines = coder_allowed_tools()
    assert len(lines) == 2
    assert all("${{ env.ALLOWED_FS_READ }}" in line for line in lines)
