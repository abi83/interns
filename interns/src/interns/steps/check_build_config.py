"""Detects whether a repo's Makefile still has the unfilled test/build stub,
so the pipeline can nudge the repo owner on the issue instead of either
failing every PR or saying nothing.

Deterministic and independent of what the coder did or said this run -- it
greps the Makefile on disk, it doesn't trust the agent's word for it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .. import cli

MARKER = b"INTERNS: not configured"


def is_configured(repo_root: str) -> bool:
    """False when there's no Makefile at all, or the stub marker is still
    present in it.

    Reads raw bytes rather than decoded text -- like the bash version's
    `grep -F`, this doesn't care what encoding a consumer's Makefile is in,
    and decoding it would crash the step on one that isn't valid UTF-8."""
    makefile = Path(repo_root) / "Makefile"
    if not makefile.is_file():
        return False
    return MARKER not in makefile.read_bytes()


def _main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pipeline.check_build_config")
    parser.add_argument("repo_root")
    args = parser.parse_args(argv)

    configured = is_configured(args.repo_root)
    cli.write_output("configured", configured)
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(_main))
