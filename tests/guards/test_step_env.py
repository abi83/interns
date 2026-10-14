"""Each workflow step that runs `interns.entrypoint <cmd>` supplies the env the
command requires, and each command declares everything its code reads.

The declaration is `ENV_SPEC` in the command's module (see `interns.env_spec`).
Two checks tie it to reality: the workflows are parsed and every step's visible
env must cover the spec, and the module's AST must not read an env var the spec
omits. Needs the `yq` binary (the pipeline's own prerequisite) to parse YAML.
"""

from __future__ import annotations

import ast
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from interns import ctx, entrypoint
from interns.env_spec import EnvSpec

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "interns/src/interns"
WORKFLOWS = sorted((ROOT / ".github/workflows").glob("*.yml"))
ACTIONS = sorted((ROOT / ".github/actions").glob("*/action.yml"))

INVOCATION = re.compile(r"interns\.entrypoint\b(.*)")
# Names GitHub sets for every step; anything else must come from an `env:` block.
STANDARD_ENV = re.compile(r"CI|GITHUB_\w+|RUNNER_\w+")


@dataclass(frozen=True)
class Invocation:
    where: str
    command: str
    argv: list[str]
    supplied: frozenset[str]

    def missing(self) -> frozenset[str]:
        needed = entrypoint.required_env(self.command, self.argv)
        return frozenset(n for n in needed if n not in self.supplied and not STANDARD_ENV.fullmatch(n))


def load_yaml(path: Path) -> dict:
    result = subprocess.run(["yq", "-o=json", ".", str(path)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def logical_lines(run: str) -> list[str]:
    lines = run.replace("\\\n", " ").splitlines()
    return [line for line in lines if not line.lstrip().startswith("#")]


def command_tokens(rest: str) -> list[str]:
    """Tokens of one invocation: up to the first shell operator (`>`, `|`, `)`, `;`, `&&`)."""
    lexer = shlex.shlex(rest, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    tokens: list[str] = []
    for token in lexer:
        if all(c in lexer.punctuation_chars for c in token):
            break
        tokens.append(token)
    return tokens


def invocations_in(run: str) -> list[tuple[str, list[str]]]:
    found = []
    for line in logical_lines(run):
        match = INVOCATION.search(line)
        if not match:
            continue
        tokens = command_tokens(match.group(1))
        assert tokens, f"interns.entrypoint without a command: {line.strip()}"
        found.append((tokens[0], tokens[1:]))
    return found


def env_names(block: dict | None) -> frozenset[str]:
    return frozenset((block or {}).get("env") or {})


def action_name(uses: str) -> str | None:
    match = re.fullmatch(r"\./.*\.github/actions/([\w-]+)", uses)
    return match.group(1) if match else None


def step_label(step: dict, index: int) -> str:
    return step.get("name") or step.get("id") or f"step {index}"


def workflow_steps(path: Path):
    """(label, step, env visible to the step) for every step of every job."""
    doc = load_yaml(path)
    for job_id, job in doc["jobs"].items():
        outer = env_names(doc) | env_names(job)
        for i, step in enumerate(job.get("steps", [])):
            yield f"{path.name}:{job_id}:{step_label(step, i)}", step, outer | env_names(step)


def action_callers() -> dict[str, list[frozenset[str]]]:
    """Composite action name -> env visible at each site that uses it; its steps inherit that env."""
    callers: dict[str, list[frozenset[str]]] = {}
    for path in WORKFLOWS:
        for _, step, visible in workflow_steps(path):
            name = action_name(step.get("uses", ""))
            if name:
                callers.setdefault(name, []).append(visible)
    return callers


def all_invocations() -> list[Invocation]:
    found = []
    for path in WORKFLOWS:
        for label, step, visible in workflow_steps(path):
            for command, argv in invocations_in(step.get("run", "")):
                found.append(Invocation(label, command, argv, visible))
    callers = action_callers()
    for path in ACTIONS:
        name = path.parent.name
        for i, step in enumerate(load_yaml(path)["runs"]["steps"]):
            for command, argv in invocations_in(step.get("run", "")):
                for caller_env in callers.get(name, [frozenset()]):
                    label = f"action {name}:{step_label(step, i)}"
                    found.append(Invocation(label, command, argv, caller_env | env_names(step)))
    return found


INVOCATIONS = all_invocations()


def test_workflows_run_entrypoint_commands():
    assert len(INVOCATIONS) > 40


@pytest.mark.parametrize("inv", INVOCATIONS, ids=lambda i: f"{i.where}:{i.command}")
def test_step_supplies_required_env(inv: Invocation):
    assert not inv.missing(), f"{inv.where}: `{inv.command}` requires {sorted(inv.missing())} but the step does not supply it"


def test_detects_a_step_missing_a_required_variable(monkeypatch: pytest.MonkeyPatch):
    # The refine job's run-summary step, with the reviewer bot required on every phase.
    refine = Invocation("x", "run-summary", ["--phase", "Refinement"], frozenset({"GH_TOKEN"}))
    assert not refine.missing()
    monkeypatch.setattr(entrypoint, "env_spec", lambda command: EnvSpec.of("REVIEWER_BOT"))
    assert refine.missing() == {"REVIEWER_BOT"}


def test_env_visible_from_workflow_job_and_step():
    doc = {"env": {"A": "1"}, "jobs": {"j": {"env": {"B": "2"}, "steps": [{"run": "x", "env": {"C": "3"}}]}}}
    assert env_names(doc) | env_names(doc["jobs"]["j"]) | env_names(doc["jobs"]["j"]["steps"][0]) == {"A", "B", "C"}


def test_parses_arguments_up_to_the_first_shell_operator():
    run = 'x=$(python3 -m interns.entrypoint gh-query --query head-ref --number "$PR")\n'
    assert invocations_in(run) == [("gh-query", ["--query", "head-ref", "--number", "$PR"])]
    folded = 'python3 -m interns.entrypoint run-summary --phase Review \\\n  --pr 3 > out.json\n'
    assert invocations_in(folded) == [("run-summary", ["--phase", "Review", "--pr", "3"])]


# --- the declaration covers what the code reads --------------------------------


def _literal_env_reads(node: ast.AST) -> set[str]:
    reads: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and _is_require_env(sub.func) and sub.args and isinstance(sub.args[0], ast.Constant):
            reads.add(str(sub.args[0].value))
        if isinstance(sub, ast.Subscript) and ast.unparse(sub.value) == "os.environ" and isinstance(sub.slice, ast.Constant):
            reads.add(str(sub.slice.value))
    return reads


def _is_require_env(func: ast.expr) -> bool:
    return ast.unparse(func) in {"cli.require_env", "require_env"}


def _function_env(tree: ast.Module | ast.ClassDef, receiver: str) -> dict[str, set[str]]:
    """Function name -> env it reads, directly or through sibling calls via `receiver` (`self.x` / bare name)."""
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    direct = {name: _literal_env_reads(fn) for name, fn in functions.items()}
    calls = {
        name: {
            ref
            for sub in ast.walk(fn)
            for ref in _sibling_refs(sub, receiver)
            if ref in functions
        }
        for name, fn in functions.items()
    }
    closed = {name: set(reads) for name, reads in direct.items()}
    changed = True
    while changed:
        changed = False
        for name, refs in calls.items():
            for ref in refs:
                if not closed[ref] <= closed[name]:
                    closed[name] |= closed[ref]
                    changed = True
    return closed


def _sibling_refs(node: ast.AST, receiver: str) -> list[str]:
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == receiver:
        return [node.attr]
    if receiver == "" and isinstance(node, ast.Name):
        return [node.id]
    return []


def _parse(relative: str) -> ast.Module:
    return ast.parse((PACKAGE / relative).read_text())


CTX_CLASS = next(n for n in _parse("ctx.py").body if isinstance(n, ast.ClassDef) and n.name == "ActionsCtx")
CTX_ENV_BY_MEMBER = _function_env(CTX_CLASS, "self")
CLI_ENV_BY_FUNCTION = _function_env(_parse("cli.py"), "")


def code_env_reads(module_path: str) -> set[str]:
    tree = _parse(module_path)
    reads = _literal_env_reads(tree)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)):
            continue
        if node.value.id == "ctx":
            reads |= CTX_ENV_BY_MEMBER.get(node.attr, set())
        if node.value.id == "cli":
            reads |= CLI_ENV_BY_FUNCTION.get(node.attr, set())
    return reads


COMMANDS = sorted({*entrypoint._COMMANDS, *entrypoint._ENV_FREE_COMMANDS})


@pytest.mark.parametrize("command", COMMANDS)
def test_command_spec_covers_what_its_code_reads(command: str):
    module = sys.modules[{**entrypoint._COMMANDS, **entrypoint._ENV_FREE_COMMANDS}[command].__module__]
    reads = code_env_reads(f"steps/{module.__name__.rsplit('.', 1)[-1]}.py")
    declared = entrypoint.env_spec(command).every_path()
    base = ctx.CTX_ENV if command in entrypoint._COMMANDS else frozenset()
    undeclared = reads - declared - base
    assert not undeclared, f"{command}: reads {sorted(undeclared)} but ENV_SPEC does not declare it"


def test_detects_an_undeclared_read():
    tree = ast.parse('def main(ctx, argv):\n    cli.require_env("NEW_VAR")\n    ctx.reviewer_bot\n    cli.write_output("a", "b")\n')
    reads = _literal_env_reads(tree)
    assert reads == {"NEW_VAR"}
    assert CTX_ENV_BY_MEMBER["reviewer_bot"] == {"REVIEWER_BOT"}
    assert CLI_ENV_BY_FUNCTION["write_output"] == {"GITHUB_OUTPUT"}
    assert CTX_ENV_BY_MEMBER["run_url"] == {"GITHUB_RUN_ID"}
