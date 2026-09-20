"""Detects whether a repo's Makefile still has the unfilled test/build stub,
so the pipeline can nudge the repo owner on the issue instead of either
failing every PR or saying nothing.

Deterministic and independent of what the coder did or said this run -- it
greps the Makefile on disk, it doesn't trust the agent's word for it.

check-build-config.sh is a thin shim over this module.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "INTERNS: not configured"


def is_configured(repo_root: str) -> bool:
    """False when there's no Makefile at all, or the stub marker is still
    present in it."""
    makefile = Path(repo_root) / "Makefile"
    if not makefile.is_file():
        return False
    return MARKER not in makefile.read_text()


def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="python -m pipeline.check_build_config")
    parser.add_argument("repo_root")
    args = parser.parse_args(argv)

    configured = is_configured(args.repo_root)
    output_path = os.environ["GITHUB_OUTPUT"]
    with open(output_path, "a") as f:
        f.write(f"configured={'true' if configured else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
