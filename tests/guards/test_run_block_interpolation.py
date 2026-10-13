"""No `run:` block splices free-text values into shell source via `${{ }}`.

`${{ }}` is expanded before the shell parses the script, so a value containing
quotes, `$(...)` or backticks breaks out of the quoting. Free text (check
names, branch names, titles, bodies, reasons) must reach the script through
`env:` and be read as `"$VAR"`. Only expressions that cannot carry shell
metacharacters are allowed inline.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = sorted((ROOT / ".github/workflows").glob("*.yml")) + sorted((ROOT / ".github/actions").glob("*/action.yml"))

STEP_OUTPUTS = "number|pr_number|issue_number|execution_file|configured|cost_warn_usd|app-slug|draft_pr_url"
# The pipeline_ref input is pinned by the consumer's caller workflow, not by
# issue/PR content; the plan outputs and the number inputs they feed are
# integers parsed from the event.
ALLOWED = [
    re.compile(p)
    for p in (
        r"github\.(repository|workspace|token)",
        r"github\.event\.pull_request\.merged",
        r"runner\.temp",
        r"inputs\.(pr_number|issue_number|pipeline_ref)",
        r"needs\.plan\.outputs\.(issue|pr)",
        rf"steps\.\w+\.outputs\.({STEP_OUTPUTS})",
        r"steps\.verify_pr\.outputs\.pr_number \|\| steps\.pr\.outputs\.pr_number",
        r"needs\.plan\.outputs\.fix_round == 'true' && 'fix' \|\| 'initial'",
    )
]


def run_blocks(text: str) -> list[tuple[int, str]]:
    """(line number, text) for every line belonging to a `run:` scalar."""
    lines = text.split("\n")
    found: list[tuple[int, str]] = []
    indent = None
    for number, line in enumerate(lines, 1):
        opener = re.match(r"^(\s*)(- )?run:\s*(.*)$", line)
        if opener:
            indent = len(opener.group(1)) + (2 if opener.group(2) else 0)
            found.append((number, opener.group(3)))
            continue
        if indent is None:
            continue
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            indent = None
            continue
        found.append((number, line))
    return found


def violations(text: str) -> list[str]:
    bad = []
    for number, line in run_blocks(text):
        for expr in re.findall(r"\$\{\{\s*(.*?)\s*\}\}", line):
            if not any(p.fullmatch(expr) for p in ALLOWED):
                bad.append(f"line {number}: ${{{{ {expr} }}}}")
    return bad


def test_no_run_block_interpolates_free_text():
    problems = {f.relative_to(ROOT).as_posix(): violations(f.read_text()) for f in FILES}
    problems = {name: v for name, v in problems.items() if v}
    assert not problems, f"pass these through env: instead: {problems}"


def test_guard_flags_a_step_output_spliced_into_a_run_block():
    text = 'steps:\n  - run: >\n      tool --reason "${{ steps.checks.outputs.reason }}"\n  - name: x\n    uses: y\n'
    assert violations(text) == ["line 3: ${{ steps.checks.outputs.reason }}"]


def test_guard_accepts_values_read_from_env():
    text = 'steps:\n  - env:\n      REASON: ${{ steps.checks.outputs.reason }}\n    run: tool --reason "$REASON"\n'
    assert violations(text) == []
