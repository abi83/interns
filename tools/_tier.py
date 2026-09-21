"""Runs one test tier under coverage and enforces its floor from pyproject.toml."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COVERAGE_DIR = ROOT / ".coverage"


def _floor(tier: str) -> int:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return config["tool"]["interns-tests"]["floors"][tier]


def _run(*args: str, env: dict[str, str]) -> int:
    return subprocess.run([sys.executable, "-m", *args], cwd=ROOT, env=env).returncode


def run_tier(tier: str, pytest_args: list[str], extra_env: dict[str, str] | None = None) -> int:
    shutil.rmtree(COVERAGE_DIR, ignore_errors=True)
    env = {**os.environ, "COVERAGE_FILE": str(COVERAGE_DIR / "data"), **(extra_env or {})}

    if _run("coverage", "run", "-m", "pytest", *pytest_args, env=env) != 0:
        return 1
    if _run("coverage", "combine", "--quiet", env=env) != 0:
        return 1
    floor = _floor(tier)
    print(f"\n{tier} tier: coverage floor {floor}%")
    return _run("coverage", "report", f"--fail-under={floor}", env=env)
