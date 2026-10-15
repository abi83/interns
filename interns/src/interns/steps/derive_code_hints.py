"""Derives `commit_type_hint` (`fix:` / `feat:`) and `branch` (`<prefix>/issue-<n>-<slug>`)
for the initial coder run, so the agent doesn't spend reasoning inventing them.

Runs after the issue-type gate, which guarantees a type:coding-task or type:bug label.
"""

from __future__ import annotations

import re
import sys

from .. import cli, gh
from ..domain import labels
from ..ctx import ActionsCtx
from ..env_spec import EnvSpec

ENV_SPEC = EnvSpec.of("GITHUB_OUTPUT")


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:40].rstrip("-")


def derive_code_hints(repo: str, issue: int) -> tuple[str, str]:
    current = set(labels.issue_labels(repo, issue))
    if labels.TYPE_BUG in current:
        prefix = "fix"
    elif labels.TYPE_CODING_TASK in current:
        prefix = "feat"
    else:
        raise ValueError(
            f"issue #{issue} has neither type:bug nor type:coding-task (labels: {','.join(current)})"
        )

    title = gh.issue_view(repo, issue, ["title"])["title"]
    return f"{prefix}:", f"{prefix}/issue-{issue}-{_slug(title)}"


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("derive-code-hints")
    parser.add_argument("--issue", type=int, required=True)
    args = parser.parse_args(argv)

    try:
        commit_type_hint, branch = derive_code_hints(ctx.repo, args.issue)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    cli.write_output("commit_type_hint", commit_type_hint)
    cli.write_output("branch", branch)
    return 0
