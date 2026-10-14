"""Concatenates prompt files into a single `$GITHUB_OUTPUT` value, so a
workflow can inline real instructions straight into a Claude prompt instead
of telling the agent to Read them itself -- the agent otherwise burns a
guaranteed tool call per file just to learn its own task, every run (see
abi83/interns#98's investigation).
"""

from __future__ import annotations

from pathlib import Path

from .. import cli
from ..env_spec import EnvSpec

ENV_SPEC = EnvSpec.of("GITHUB_OUTPUT")


def build_output(name: str, files: list[str]) -> bytes:
    """A `$GITHUB_OUTPUT`-formatted `name<<DELIM` block holding the
    concatenated contents of `files`.

    Reads/writes raw bytes rather than decoded text -- like the bash
    version's `cat`, a prompt file's encoding is none of this script's
    business, and decoding it would crash the step on a byte sequence
    invalid in the runner's default encoding.
    """
    content = b"".join(Path(f).read_bytes() for f in files)
    return cli.github_output_block(name, content)


def main(argv: list[str]) -> int:
    parser = cli.build_parser("prompt")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)

    cli.append_output(build_output("text", args.files))
    return 0

