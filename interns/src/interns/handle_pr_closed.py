"""Runs when a coder/reviewer PR closes. Nothing else in the pipeline reacts
to a close, so without this the linked issue keeps status:in-progress
forever: on a merge GitHub's `Closes #N` shuts the issue but leaves the
label, and an unmerged close leaves the issue open with no agent owning it.

  merged            -> drop status:in-progress from the (already closed) issue
  closed, unmerged  -> move the issue status:in-progress -> status:needs-attention
                       and comment that a human needs to decide what happens next

Either way, clear any stale pr:* label from the PR.
"""

from __future__ import annotations

from . import cli, gh, labels
from .ctx import ActionsCtx


def handle_pr_closed(repo: str, pr: int, issue: int | None, merged: bool, *, server_url: str, run_url: str) -> None:
    labels.set_pr_pipeline_label(repo, pr)

    if issue is None:
        return

    if merged:
        # The issue is already closed by `Closes #N`; just retire the run label.
        labels.edit_issue_labels(repo, issue, remove=[labels.STATUS_IN_PROGRESS])
        return

    labels.set_issue_status(repo, issue, labels.STATUS_NEEDS_ATTENTION)
    gh.issue_comment(
        repo, issue,
        f"[PR #{pr}]({server_url}/{repo}/pull/{pr}) was closed without merging — this issue needs a human to "
        f"decide whether to re-dispatch the coder (re-apply `status:ready`) or drop it. Run: {run_url}",
    )


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="interns.entrypoint handle-pr-closed")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--issue", default="")
    parser.add_argument("--merged", required=True)
    args = parser.parse_args(argv)

    handle_pr_closed(
        ctx.repo,
        args.pr,
        cli.optional_int(args.issue),
        args.merged == "true",
        server_url=ctx.server_url,
        run_url=ctx.run_url(),
    )
    return 0
