"""Runs after a successful coder phase. If a PR now references the issue,
hand it to the reviewer (the issue stays status:in-progress for the whole
active run -- the pr:* label is the only "which agent" signal, and a red
check or rejection is read from native PR state, not a label). If no PR was
left, the agent stopped for clarification or partway through -- flag it for
a human.
"""

from __future__ import annotations

import sys

from . import actions_env, gh, labels


def handoff(repo: str, issue: int, pr: int | None) -> None:
    if pr is not None:
        labels.set_pr_pipeline_label(repo, pr, "pr:in-review")
        return
    labels.set_issue_status(repo, issue, "status:needs-attention")
    gh.issue_comment(
        repo, issue,
        "Coder run completed without leaving an open PR referencing this "
        f"issue — likely stopped for clarification or partway through. "
        f"See the run: {actions_env.run_url(repo)}",
    )


def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="python -m pipeline.handoff_to_review")
    parser.add_argument("issue", type=int)
    parser.add_argument("pr", nargs="?", default=None)
    args = parser.parse_args(argv)

    pr = int(args.pr) if args.pr else None
    handoff(os.environ["GITHUB_REPOSITORY"], args.issue, pr)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
