"""Command modules share one parser helper and one dispatch path:

- parsers come from `cli.build_parser`, built with the registered command name;
- no function-local `import argparse`, no hand-built `ArgumentParser`;
- `INTERNS_CONFIG` is read in one place (`config.config_path`);
- `entrypoint` imports no underscore-prefixed names;
- no `prog` string mentions the retired `pipeline` package.
"""

import ast
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "interns/src/interns"
CLI = PACKAGE / "cli.py"
ENTRYPOINT = PACKAGE / "entrypoint.py"
CONFIG = PACKAGE / "config.py"


def _modules() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py"))


def local_argparse_imports(source: str) -> list[int]:
    found = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(function):
            imports_argparse = isinstance(node, ast.Import) and any(a.name == "argparse" for a in node.names)
            from_argparse = isinstance(node, ast.ImportFrom) and node.module == "argparse"
            if imports_argparse or from_argparse:
                found.append(node.lineno)
    return found


def hand_built_parsers(source: str) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and (getattr(node.func, "attr", None) == "ArgumentParser" or getattr(node.func, "id", None) == "ArgumentParser")
    ]


def build_parser_names(source: str) -> list[str]:
    return [
        node.args[0].value
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and getattr(node.func, "attr", None) == "build_parser"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    ]


def underscore_imports(source: str) -> list[str]:
    tree = ast.parse(source)
    from_imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name.startswith("_")
    ]
    attributes = [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr.startswith("_")]
    return from_imports + attributes


def registered_commands() -> set[str]:
    tree = ast.parse(ENTRYPOINT.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") in {"_COMMANDS", "_ENV_FREE_COMMANDS"}:
            names |= {key.value for key in node.value.keys}
    return names


def test_detects_violations():
    assert local_argparse_imports("def f():\n    import argparse\n") == [2]
    assert local_argparse_imports("import argparse\n") == []
    assert hand_built_parsers("import argparse\np = argparse.ArgumentParser(prog='x')\n") == [2]
    assert underscore_imports("from .a import _main\nx = a._main\n") == ["_main", "_main"]
    assert build_parser_names('p = cli.build_parser("labels")\n') == ["labels"]


def test_no_function_local_argparse_import():
    offenders = [f"{p.relative_to(PACKAGE)}:{n}" for p in _modules() for n in local_argparse_imports(p.read_text())]
    assert not offenders, f"import argparse at module top, or use cli.build_parser: {offenders}"


def test_parsers_are_built_by_the_shared_helper_only():
    offenders = [f"{p.relative_to(PACKAGE)}:{n}" for p in _modules() if p != CLI for n in hand_built_parsers(p.read_text())]
    assert not offenders, f"use cli.build_parser(<command>): {offenders}"


def test_every_parser_is_built_for_a_registered_command():
    registered = registered_commands()
    offenders = [
        f"{p.relative_to(PACKAGE)}: {name}"
        for p in _modules()
        for name in build_parser_names(p.read_text())
        if name not in registered
    ]
    assert not offenders, f"not registered in entrypoint: {offenders}"


def test_interns_config_is_read_in_one_place():
    readers = [p.relative_to(PACKAGE).as_posix() for p in _modules() if "INTERNS_CONFIG" in p.read_text()]
    assert readers == ["config.py"], readers
    assert len(re.findall(r"INTERNS_CONFIG", CONFIG.read_text())) == 1


def test_entrypoint_imports_no_underscore_names():
    assert underscore_imports(ENTRYPOINT.read_text()) == []


def test_no_prog_string_mentions_pipeline():
    offenders = [
        f"{p.relative_to(PACKAGE)}:{n.lineno}"
        for p in _modules()
        for n in ast.walk(ast.parse(p.read_text()))
        if isinstance(n, ast.keyword) and n.arg == "prog" and "pipeline" in ast.unparse(n.value)
    ]
    assert not offenders, offenders
