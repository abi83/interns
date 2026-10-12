"""Every registered command's `main` lives in `interns/steps/<module>.py`, and
no step module shares a basename with a domain module."""

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "interns/src/interns"
ENTRYPOINT = PACKAGE / "entrypoint.py"
TABLES = {"_COMMANDS", "_ENV_FREE_COMMANDS"}


def command_modules(source: str) -> dict[str, str]:
    """Registered command -> name of the module whose `main` it dispatches to."""
    modules: dict[str, str] = {}
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") in TABLES):
            continue
        assert isinstance(node.value, ast.Dict)
        for key, value in zip(node.value.keys, node.value.values, strict=True):
            assert isinstance(key, ast.Constant)
            assert isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name) and value.attr == "main"
            modules[str(key.value)] = value.value.id
    return modules


def steps_imports(source: str) -> set[str]:
    return {
        alias.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "steps"
        for alias in node.names
    }


def stems(directory: str) -> set[str]:
    return {p.stem for p in (PACKAGE / directory).glob("*.py")} - {"__init__"}


def test_detects_a_command_outside_steps():
    source = "from . import config\n_COMMANDS: dict = {'config': config.main}\n"
    assert command_modules(source) == {"config": "config"}
    assert steps_imports(source) == set()


def test_every_registered_command_lives_in_a_steps_module():
    source = ENTRYPOINT.read_text()
    imported = steps_imports(source)
    offenders = {c: m for c, m in command_modules(source).items() if m not in imported or m not in stems("steps")}
    assert not offenders, f"command mains must come from interns/steps/<module>.py: {offenders}"


def test_no_module_basename_is_shared_between_steps_and_domain():
    clashes = stems("steps") & stems("domain")
    assert not clashes, f"rename the step wrapper: {sorted(clashes)}"
