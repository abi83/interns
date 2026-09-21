"""A red PR check goes straight to a human, no coder retry loop (#133).
"""

from __future__ import annotations

import sys

from . import actions_env, gh, labels


def route_red_checks(repo: str, pr: int, issue: int | None, reason: str) -> None:
    labels.escalate_pr(repo, pr)
    gh.pr_comment(
        repo, pr,
        f"PR checks are not green ({reason}) — the reviewer won't run. The coder writes and runs "
        "tests before pushing, so this is being sent straight to a human rather than retried. "
        f"Run: {actions_env.run_url(repo)}",
    )
    if issue is not None:
        labels.set_issue_status(repo, issue, labels.STATUS_NEEDS_ATTENTION)


def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="python -m pipeline.route_red_checks")
    parser.add_argument("pr", type=int)
    parser.add_argument("issue")
    parser.add_argument("reason")
    args = parser.parse_args(argv)

    route_red_checks(
        os.environ["GITHUB_REPOSITORY"],
        args.pr,
        int(args.issue) if args.issue else None,
        args.reason,
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
