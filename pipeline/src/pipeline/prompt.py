"""Concatenates prompt files into a single `$GITHUB_OUTPUT` value, so a
workflow can inline real instructions straight into a Claude prompt instead
of telling the agent to Read them itself -- the agent otherwise burns a
guaranteed tool call per file just to learn its own task, every run (see
abi83/interns#98's investigation).

load-prompt.sh is a thin shim over this module.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path


def build_output(name: str, files: list[str]) -> str:
    """A `$GITHUB_OUTPUT`-formatted `name<<DELIM` block holding the
    concatenated contents of `files`. The delimiter is randomized and
    resampled until it doesn't collide with the content -- a fixed delimiter
    would silently truncate a prompt file that happens to contain it."""
    text = "".join(Path(f).read_text() for f in files)
    delim = f"ghadelim_{secrets.token_hex(16)}"
    while delim in text:
        delim = f"ghadelim_{secrets.token_hex(16)}"
    return f"{name}<<{delim}\n{text}\n{delim}\n"


def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="python -m pipeline.prompt")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)

    output_path = os.environ["GITHUB_OUTPUT"]
    with open(output_path, "a") as f:
        f.write(build_output("text", args.files))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
