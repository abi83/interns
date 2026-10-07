"""Installs the consumer repo's dependencies via `make setup` before the coder
runs, so the agent never has to bootstrap its own environment.

A repo with no `setup` target, or one still carrying the stub marker, is
skipped with a warning. A failing `setup` raises -- the job must fail before
any Claude tokens are spent.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from .. import cli
from .check_build_config import MARKER

_SETUP_TARGET = re.compile(rb"^setup\s*:", re.MULTILINE)


def has_setup_target(repo_root: str) -> bool:
    makefile = Path(repo_root) / "Makefile"
    if not makefile.is_file():
        return False
    return _SETUP_TARGET.search(makefile.read_bytes()) is not None


def run_setup(repo_root: str) -> bool:
    """True when real setup ran; False when it was skipped (warning emitted)."""
    if not has_setup_target(repo_root):
        print("::warning::No `setup` target in Makefile -- dependencies not installed before the coder runs.")
        return False
    proc = subprocess.run(["make", "setup"], cwd=repo_root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    sys.stdout.buffer.write(proc.stdout)
    sys.stdout.flush()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, proc.args)
    if MARKER in proc.stdout:
        print("::warning::`make setup` is not configured -- dependencies not installed before the coder runs.")
        return False
    return True


def _main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m interns.steps.run_setup")
    parser.add_argument("repo_root")
    args = parser.parse_args(argv)

    run_setup(args.repo_root)
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(_main))
