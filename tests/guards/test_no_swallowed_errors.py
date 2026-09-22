"""Fail on `except ...: return <default>` anywhere in the pipeline package
except best_effort.py, which is the one permitted place.

Also fail on best_effort.call() with an empty reason string -- empty reasons
make the warning useless.
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "interns/src/interns"


def is_default(value: ast.expr | None) -> bool:
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return not (type(value.value) is int and value.value != 0)
    if isinstance(value, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
        return all(is_default(child) for child in ast.iter_child_nodes(value) if isinstance(child, ast.expr))
    return False


def swallowing_handlers(source: str) -> list[tuple[str, int]]:
    """(function name, line) of each handler that returns a default instead of raising."""
    found = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for handler in (n for n in ast.walk(function) if isinstance(n, ast.ExceptHandler)):
            inside = [n for statement in handler.body for n in ast.walk(statement)]
            raises = any(isinstance(n, ast.Raise) for n in inside)
            returns_default = any(isinstance(n, ast.Return) and is_default(n.value) for n in inside)
            if returns_default and not raises:
                found.append((function.name, handler.lineno))
    return found


def test_detects_a_swallowed_error():
    source = "def f():\n    try:\n        g()\n    except ValueError:\n        return []\n"
    assert swallowing_handlers(source) == [("f", 4)]


@pytest.mark.parametrize("handler_body", ["return False", "return 0", "if x:\n            return None"])
def test_detects_falsy_and_nested_defaults(handler_body):
    source = f"def f():\n    try:\n        g()\n    except ValueError:\n        {handler_body}\n"
    assert swallowing_handlers(source) == [("f", 4)]


@pytest.mark.parametrize("handler_body", ["return 1", "raise", "raise X() from exc"])
def test_ignores_exit_codes_and_reraises(handler_body):
    source = f"def f():\n    try:\n        g()\n    except ValueError as exc:\n        {handler_body}\n"
    assert swallowing_handlers(source) == []


def _best_effort_calls_with_empty_reason(source: str) -> list[int]:
    """Line numbers of best_effort.call() with an empty reason string."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "call" and
                isinstance(func.value, ast.Name) and func.value.id == "best_effort"):
            continue
        if node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == "":
            found.append(node.lineno)
    return found


def test_no_swallowed_errors_outside_the_mechanism():
    found = {
        (path.name, function)
        for path in PACKAGE.glob("*.py")
        if path.name != "best_effort.py"
        for function, _ in swallowing_handlers(path.read_text())
    }
    assert found == set(), "new `except: return <default>`; raise instead or use best_effort.call"


def test_no_empty_reason_in_best_effort_calls():
    found = [
        (path.name, line)
        for path in PACKAGE.glob("*.py")
        if path.name != "best_effort.py"
        for line in _best_effort_calls_with_empty_reason(path.read_text())
    ]
    assert found == [], f"best_effort.call with empty reason string: {found}"
