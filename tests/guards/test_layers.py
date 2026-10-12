"""Enforces import-direction rules for the interns layering.

Layer order:
  interns.gh.transport  ->  interns.gh.ops  ->  interns.domain  ->  adapters
                                                 |- pipeline steps (interns.steps)
                                                 |- MCP server (gh_issues_mcp/server.py)
                                                 `- Actions entrypoint (interns.entrypoint)

Rules:
  1. interns.gh.transport imports no other interns module.
  2. interns.gh imports nothing from domain, steps or entrypoint.
  3. interns.domain imports nothing from steps, entrypoint, ctx or mcp.
  4. A step imports no other step, and neither entrypoint nor mcp.
  5. Shared top-level modules (execution, config, ...) import
     neither steps nor entrypoint.
  6. The MCP server imports nothing from steps, entrypoint or ctx.
  7. Domain, steps and the MCP server use `interns.gh` ops only --
     they never import `interns.gh.transport`, and `interns.gh` exposes no
     transport primitive.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTERNS_SRC = ROOT / "interns" / "src" / "interns"
MCP_SERVER = ROOT / "gh_issues_mcp" / "server.py"

TOP_LEVEL_ENTRYPOINT = "entrypoint.py"


def _resolved_imports(path: Path, package: str) -> list[str]:
    tree = ast.parse(path.read_text())
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            if level == 0:
                if node.module:
                    modules.append(node.module)
                    for alias in node.names:
                        modules.append(f"{node.module}.{alias.name}")
            else:
                base_parts = package.split(".")
                base = ".".join(base_parts[: len(base_parts) - (level - 1)])
                if node.module:
                    modules.append(f"{base}.{node.module}")
                else:
                    for alias in node.names:
                        modules.append(f"{base}.{alias.name}")
    return modules


def _imports_any(modules: list[str], forbidden: list[str]) -> list[str]:
    hits: list[str] = []
    for imp in modules:
        for f in forbidden:
            if imp == f or imp.startswith(f + "."):
                hits.append(imp)
    return [h for h in hits if not any(o != h and o.startswith(h + ".") for o in hits)]


def _check(violations: list[str], path: Path, package: str, forbidden: list[str]) -> None:
    hits = _imports_any(_resolved_imports(path, package), forbidden)
    rel = path.relative_to(ROOT)
    for hit in hits:
        violations.append(f"{rel}: imports {hit!r}")


TRANSPORT_PRIMITIVES = ("api", "api_all_pages", "api_status", "graphql", "run")


def _modules(subpackage: str) -> list[Path]:
    paths = sorted(p for p in (INTERNS_SRC / subpackage).glob("*.py") if p.name != "__init__.py")
    assert paths, f"no modules found under {subpackage}/"
    return paths


def _top_level_modules() -> list[Path]:
    paths = sorted(
        p for p in INTERNS_SRC.glob("*.py") if p.name not in ("__init__.py", TOP_LEVEL_ENTRYPOINT)
    )
    assert paths
    return paths


def _violations(modules: list[Path], package: str, forbidden: list[str]) -> list[str]:
    violations: list[str] = []
    for path in modules:
        _check(violations, path, package, forbidden)
    return violations


def _fail_if(violations: list[str]) -> None:
    assert not violations, "Layer violations:\n" + "\n".join(sorted(violations))


def test_transport_imports_no_other_interns_module() -> None:
    _fail_if(_violations([INTERNS_SRC / "gh" / "transport.py"], "interns.gh", ["interns"]))


def test_gh_does_not_import_upper_layers() -> None:
    forbidden = ["interns.domain", "interns.steps", "interns.entrypoint", "mcp"]
    _fail_if(_violations(_modules("gh"), "interns.gh", forbidden))


def test_domain_does_not_import_adapters() -> None:
    forbidden = ["interns.steps", "interns.entrypoint", "interns.ctx", "mcp"]
    _fail_if(_violations(_modules("domain"), "interns.domain", forbidden))


def test_steps_do_not_import_each_other_or_adapters() -> None:
    steps = _modules("steps")
    violations: list[str] = []
    for path in steps:
        other_steps = [f"interns.steps.{p.stem}" for p in steps if p != path]
        _check(violations, path, "interns.steps", other_steps + ["interns.entrypoint", "mcp"])
    _fail_if(violations)


def test_shared_top_level_modules_do_not_import_steps_or_entrypoint() -> None:
    _fail_if(_violations(_top_level_modules(), "interns", ["interns.steps", "interns.entrypoint"]))


def test_mcp_server_imports_neither_steps_entrypoint_nor_ctx() -> None:
    forbidden = ["interns.steps", "interns.entrypoint", "interns.ctx"]
    _fail_if(_violations([MCP_SERVER], "", forbidden))


def test_ops_only_callers_never_import_transport() -> None:
    modules = [
        *((p, "interns.domain") for p in _modules("domain")),
        *((p, "interns.steps") for p in _modules("steps")),
                (MCP_SERVER, ""),
    ]
    violations: list[str] = []
    for path, package in modules:
        _check(violations, path, package, ["interns.gh.transport"])
    _fail_if(violations)


def test_gh_package_exposes_no_transport_primitives() -> None:
    from interns import gh

    leaked = [name for name in TRANSPORT_PRIMITIVES if hasattr(gh, name)]
    assert not leaked, f"interns.gh re-exports transport primitives: {leaked}"
