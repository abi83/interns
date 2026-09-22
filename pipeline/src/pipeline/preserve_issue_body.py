"""Posts the issue's pre-refinement body as a comment, so the refiner's
rewrite never loses the original text."""

from __future__ import annotations

import os

from . import gh
from .ctx import ActionsCtx


def preserve_issue_body(repo: str, issue: int, body: str) -> None:
    gh.issue_comment(
        repo, issue,
        f"<details><summary>Body before refinement</summary>\n\n{body}\n\n</details>",
    )


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="pipeline.entrypoint preserve-issue-body")
    parser.add_argument("--issue", type=int, required=True)
    args = parser.parse_args(argv)
    # os.environ, not require_env: an empty issue body is valid
    preserve_issue_body(ctx.repo, args.issue, os.environ["ISSUE_BODY"])
    return 0
