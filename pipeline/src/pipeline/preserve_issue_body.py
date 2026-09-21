"""Posts the issue's pre-refinement body as a comment, so the refiner's
rewrite never loses the original text."""

from __future__ import annotations

import os
import sys

from . import gh


def preserve_issue_body(repo: str, issue: int, body: str) -> None:
    gh.issue_comment(
        repo, issue,
        f"<details><summary>Body before refinement</summary>\n\n{body}\n\n</details>",
    )


def _main(argv: list[str]) -> int:
    repo, issue = argv
    preserve_issue_body(repo, int(issue), os.environ["ISSUE_BODY"])
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
