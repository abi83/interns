"""Runs after a coder fix round. If the agent left a ./.coder-gave-up.md
sentinel it has *declined* the task -- the feedback needs a protected path
it can't push, is out of scope for the issue, or needs an owner decision --
rather than pushing a fix. Escalate straight to a human instead of handing
the PR back to the reviewer for a wasted round (#9).

The coder step still exits 0 in this case (it's reporting, not failing), so
without this check the workflow can't tell "gave up and commented" from
"finished the fix" and would re-run the reviewer.

Emits gave_up=true|false on $GITHUB_OUTPUT so the workflow skips the
reviewer hand-off when the task was declined.
"""

from __future__ import annotations

import os
import sys

from . import actions_env, cli, gh, labels

SENTINEL_NAME = ".coder-gave-up.md"


def handle_giveup(repo: str, issue: int, pr: int | None, workspace: str) -> bool:
    sentinel = os.path.join(workspace, SENTINEL_NAME)
    if not os.path.isfile(sentinel):
        cli.write_output("gave_up", False)
        return False

    with open(sentinel) as f:
        reason = f.read().strip() or "_(no reason given)_"

    if pr is not None:
        labels.set_pr_pipeline_label(repo, pr)
    labels.set_issue_status(repo, issue, labels.STATUS_NEEDS_ATTENTION)
    gh.issue_comment(
        repo, issue,
        "The coder fix round declined this task and set `status:needs-attention` "
        "— it was not handed back to the reviewer.\n\n"
        f"{reason}\n\n"
        f"Run: {actions_env.run_url(repo)}",
    )
    cli.write_output("gave_up", True)
    return True


def _main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pipeline.handle_giveup")
    parser.add_argument("issue", type=int)
    parser.add_argument("pr", nargs="?", default="")
    args = parser.parse_args(argv)

    cli.require_env("GITHUB_OUTPUT")  # fail before the give-up side effects, not after
    handle_giveup(
        cli.require_env("GITHUB_REPOSITORY"),
        args.issue,
        cli.optional_int(args.pr),
        os.environ.get("GITHUB_WORKSPACE", "."),
    )
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(_main))
