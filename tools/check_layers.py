"""Enforces import-direction rules for the pipeline layering.

Layer order:
  gh_transport  →  core  →  adapters
                             ├─ MCP server (mcp/server.py)
                             └─ Actions entrypoint (interns.entrypoint)

Rules:
  1. gh_transport imports no other interns module.
  2. Core interns modules do not import interns.entrypoint.
  3. MCP server does not import interns.entrypoint or interns.ctx.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIPELINE_SRC = ROOT / "interns" / "src" / "interns"
MCP_SERVER = ROOT / "mcp" / "server.py"

def _resolved_imports(path: Path, package: str) -> list[str]:
    """Return absolute module names for every import in *path*.

    Relative imports (level > 0) are resolved against *package*.
    """
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
                # Resolve relative: level=1 → same package, level=2 → parent, …
                base_parts = package.split(".")
                base = ".".join(base_parts[: len(base_parts) - (level - 1)])
                if node.module:
                    modules.append(f"{base}.{node.module}")
                else:
                    # "from . import name1, name2" — record each as a submodule
                    for alias in node.names:
                        modules.append(f"{base}.{alias.name}")
    return modules


def _imports_any(modules: list[str], forbidden: list[str]) -> list[str]:
    hits: list[str] = []
    for imp in modules:
        for f in forbidden:
            if imp == f or imp.startswith(f + "."):
                hits.append(imp)
    # Drop a hit when a strictly more-specific hit from the same base is present.
    return [h for h in hits if not any(o != h and o.startswith(h + ".") for o in hits)]


def _check(violations: list[str], path: Path, package: str, forbidden: list[str]) -> None:
    hits = _imports_any(_resolved_imports(path, package), forbidden)
    rel = path.relative_to(ROOT)
    for hit in hits:
        violations.append(f"{rel}: imports {hit!r}")


def main() -> int:
    violations: list[str] = []

    # Rule 1: gh_transport must not import any other interns module.
    _check(
        violations,
        PIPELINE_SRC / "gh_transport.py",
        "interns",
        ["interns"],
    )

    # Rule 2: core modules must not import interns.entrypoint.
    core = [
        p for p in PIPELINE_SRC.glob("*.py")
        if p.name not in ("__init__.py", "entrypoint.py")
    ]
    for mod in core:
        _check(violations, mod, "interns", ["interns.entrypoint"])

    # Rule 3: MCP server must not import interns.entrypoint or interns.ctx.
    _check(
        violations,
        MCP_SERVER,
        "",  # MCP server is not inside the interns package
        ["interns.entrypoint", "interns.ctx"],
    )

    if violations:
        print("Layer violations found:", file=sys.stderr)
        for v in sorted(violations):
            print(f"  {v}", file=sys.stderr)
        return 1

    n_core = len(core)
    print(f"OK: layer checks passed ({n_core} core modules checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
