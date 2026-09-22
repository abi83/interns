"""Runs after a successful coder phase. If a PR now references the issue,
hand it to the reviewer (the issue stays status:in-progress for the whole
active run -- the pr:* label is the only "which agent" signal, and a red
check or rejection is read from native PR state, not a label). If no PR was
left, the agent stopped for clarification or partway through -- flag it for
a human.
"""

from __future__ import annotations

from . import cli, gh, labels
from .ctx import ActionsCtx


def handoff(repo: str, issue: int, pr: int | None, *, run_url: str = "") -> None:
    if pr is not None:
        labels.set_pr_pipeline_label(repo, pr, labels.PR_IN_REVIEW)
        return
    labels.set_issue_status(repo, issue, labels.STATUS_NEEDS_ATTENTION)
    gh.issue_comment(
        repo, issue,
        "Coder run completed without leaving an open PR referencing this "
        f"issue — likely stopped for clarification or partway through. "
        f"See the run: {run_url}",
    )


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="pipeline.entrypoint handoff-to-review")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--pr", default="")
    args = parser.parse_args(argv)

    handoff(ctx.repo, args.issue, cli.optional_int(args.pr), run_url=ctx.run_url())
    return 0
