"""Derives two deterministic hints for the initial coder run:
  commit_type_hint  Conventional Commit prefix for the PR title (`fix:` / `feat:`)
  branch            branch name `<prefix>/issue-<n>-<slug>` from the issue title

Both are computable from the issue's type:* label and title before the agent
starts, so the agent shouldn't spend reasoning inventing them. The push_branch
MCP tool squashes the branch on push, so the branch name is near-cosmetic. Runs after
the issue-type gate, which guarantees a type:coding-task or type:bug label.
"""

from __future__ import annotations

import re

from . import cli, gh, labels
from .ctx import ActionsCtx


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


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog="interns.entrypoint derive-code-hints")
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
