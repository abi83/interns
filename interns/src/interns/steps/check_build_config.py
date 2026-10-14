"""Detects whether a repo's Makefile still has the unfilled test/build stub,
so the pipeline can nudge the repo owner on the issue instead of either
failing every PR or saying nothing.

Deterministic and independent of what the coder did or said this run -- it
greps the Makefile on disk, it doesn't trust the agent's word for it.
"""

from __future__ import annotations


from .. import cli
from ..domain import build_config
from ..env_spec import EnvSpec

ENV_SPEC = EnvSpec.of("GITHUB_OUTPUT")


def main(argv: list[str]) -> int:
    parser = cli.build_parser("check-build-config")
    parser.add_argument("repo_root")
    args = parser.parse_args(argv)

    configured = build_config.is_configured(args.repo_root)
    cli.write_output("configured", configured)
    return 0

