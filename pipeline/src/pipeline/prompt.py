"""Concatenates prompt files into a single `$GITHUB_OUTPUT` value, so a
workflow can inline real instructions straight into a Claude prompt instead
of telling the agent to Read them itself -- the agent otherwise burns a
guaranteed tool call per file just to learn its own task, every run (see
abi83/interns#98's investigation).
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path


def github_output_block(name: str, content: bytes) -> bytes:
    """A `$GITHUB_OUTPUT`-formatted `name<<DELIM` block holding `content`.

    The delimiter is randomized and resampled until it doesn't collide with
    the content -- a fixed delimiter would silently truncate (or misparse
    the rest of $GITHUB_OUTPUT after) a value that happens to contain it.
    Any caller writing untrusted or arbitrary content -- a prompt file, a
    reviewer's comment body -- needs this, not just this module's own use.

    Exactly one newline separates the content from the closing delimiter
    line (added only if the content doesn't already end in one) -- GitHub
    Actions' multiline-output parsing treats that newline as the block's own
    line separator, not part of the value, so adding a second one would
    leave the parsed value with an extra trailing blank line.
    """
    delim = f"ghadelim_{secrets.token_hex(16)}".encode()
    while delim in content:
        delim = f"ghadelim_{secrets.token_hex(16)}".encode()
    if not content.endswith(b"\n"):
        content += b"\n"
    return f"{name}<<".encode() + delim + b"\n" + content + delim + b"\n"


def build_output(name: str, files: list[str]) -> bytes:
    """A `$GITHUB_OUTPUT`-formatted `name<<DELIM` block holding the
    concatenated contents of `files`.

    Reads/writes raw bytes rather than decoded text -- like the bash
    version's `cat`, a prompt file's encoding is none of this script's
    business, and decoding it would crash the step on a byte sequence
    invalid in the runner's default encoding.
    """
    content = b"".join(Path(f).read_bytes() for f in files)
    return github_output_block(name, content)


def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="python -m pipeline.prompt")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)

    output_path = os.environ["GITHUB_OUTPUT"]
    with open(output_path, "ab") as f:
        f.write(build_output("text", args.files))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
