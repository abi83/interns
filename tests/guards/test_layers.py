"""Enforces import-direction rules for the interns layering.

Layer order:
  interns.gh.transport  →  interns.gh.ops  →  core  →  adapters
                             ├─ MCP server (mcp/server.py)
                             └─ Actions entrypoint (interns.entrypoint)

Rules:
  1. interns.gh.transport imports no other interns module.
  2. Core interns modules do not import interns.entrypoint.
  3. MCP server does not import interns.entrypoint or interns.ctx.
  4. Steps, verdict, run_summary and the MCP server use `interns.gh` ops only —
     they never import `interns.gh.transport`, and `interns.gh` exposes no
     transport primitive.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INTERNS_SRC = ROOT / "interns" / "src" / "interns"
MCP_SERVER = ROOT / "mcp" / "server.py"


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


def test_layer_violations() -> None:
    violations: list[str] = []

    # Rule 1: transport layer imports no other interns module.
    _check(violations, INTERNS_SRC / "gh" / "transport.py", "interns.gh", ["interns"])

    # Rule 2: core modules (flat + steps/ + gh/) must not import interns.entrypoint.
    flat_core = [p for p in INTERNS_SRC.glob("*.py") if p.name not in ("__init__.py", "entrypoint.py")]
    steps_core = list((INTERNS_SRC / "steps").glob("*.py"))
    gh_core = [p for p in (INTERNS_SRC / "gh").glob("*.py") if p.name != "__init__.py"]
    pkg_map = (
        [(p, "interns") for p in flat_core]
        + [(p, "interns.steps") for p in steps_core]
        + [(p, "interns.gh") for p in gh_core]
    )
    for mod, pkg in pkg_map:
        _check(violations, mod, pkg, ["interns.entrypoint"])

    # Rule 3: MCP server must not import interns.entrypoint or interns.ctx.
    _check(violations, MCP_SERVER, "", ["interns.entrypoint", "interns.ctx"])

    # Rule 4: ops-only callers never reach for the transport layer.
    ops_only = [
        (p, "interns.steps") for p in steps_core
    ] + [(INTERNS_SRC / "verdict.py", "interns"), (INTERNS_SRC / "run_summary.py", "interns")]
    for mod, pkg in ops_only:
        _check(violations, mod, pkg, ["interns.gh.transport"])
    _check(violations, MCP_SERVER, "", ["interns.gh.transport"])

    assert not violations, "Layer violations:\n" + "\n".join(sorted(violations))


def test_gh_package_exposes_no_transport_primitives() -> None:
    from interns import gh

    leaked = [name for name in TRANSPORT_PRIMITIVES if hasattr(gh, name)]
    assert not leaked, f"interns.gh re-exports transport primitives: {leaked}"
