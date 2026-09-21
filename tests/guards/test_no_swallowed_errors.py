"""Fail on new `except ...: return <default>` in the pipeline package.

CLAUDE.md: invalid state throws -- no `catch` that swallows and returns a
default. Integer returns are exit codes (`return 1`) and don't count.
Existing sites are grandfathered in GRANDFATHERED; remove an entry when its
site is fixed, and don't add one -- wire this to the error-handling policy
once it lands.
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parents[2] / "pipeline/src/pipeline"

GRANDFATHERED = {
    ("execution.py", "result_field"),
    ("gh.py", "_paginated_names"),
    ("run_summary.py", "_issue_title"),
    ("run_summary.py", "_pr_title"),
    ("run_summary.py", "_pr_head_sha"),
    ("run_summary.py", "_issue_labels"),
    ("run_summary.py", "_pr_diff_file_count"),
    ("run_summary.py", "_coder_fix_state"),
    ("run_summary.py", "_reviewer_reviews"),
}


def is_default(value: ast.expr | None) -> bool:
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return not isinstance(value.value, (int, float))
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
            returns = [s for s in handler.body if isinstance(s, ast.Return)]
            raises = any(isinstance(s, ast.Raise) for s in handler.body)
            if returns and not raises and is_default(returns[0].value):
                found.append((function.name, handler.lineno))
    return found


def test_detects_a_swallowed_error():
    source = "def f():\n    try:\n        g()\n    except ValueError:\n        return []\n"
    assert swallowing_handlers(source) == [("f", 4)]


@pytest.mark.parametrize("handler_body", ["return 1", "raise", "raise X() from exc"])
def test_ignores_exit_codes_and_reraises(handler_body):
    source = f"def f():\n    try:\n        g()\n    except ValueError as exc:\n        {handler_body}\n"
    assert swallowing_handlers(source) == []


def test_no_new_swallowed_errors_in_the_pipeline_package():
    found = {
        (path.name, function)
        for path in PACKAGE.glob("*.py")
        for function, _ in swallowing_handlers(path.read_text())
    }
    assert found - GRANDFATHERED == set(), "new `except: return <default>`; raise instead"
    assert GRANDFATHERED - found == set(), "fixed sites: drop them from GRANDFATHERED"
