"""Read-only GitHub lookups for workflow YAML: one value per subcommand,
printed for `$(...)` capture or appended to `$GITHUB_OUTPUT`."""

from __future__ import annotations

import argparse
import sys

from . import cli, gh


def head_ref(repo: str, pr: int) -> str:
    return gh.pr_view(repo, pr, ["headRefName"])["headRefName"]


def head_sha(repo: str, pr: int) -> str:
    return gh.pr_view(repo, pr, ["headRefOid"])["headRefOid"]


def closing_issue(repo: str, pr: int) -> str:
    """Number of the first issue `pr` closes; empty when none. A PR with no
    linked issue is expected (any human-opened PR is still reviewed)."""
    refs = gh.pr_view(repo, pr, ["closingIssuesReferences"])["closingIssuesReferences"]
    return str(refs[0]["number"]) if refs else ""


def pr_for_issue(repo: str, issue: int) -> dict[str, str]:
    """`pr_number` / `head_ref` of the first open PR closing `issue`; both
    empty when there is none."""
    for pr in gh.pr_list(repo, ["number", "headRefName", "closingIssuesReferences"]):
        if any(ref["number"] == issue for ref in pr["closingIssuesReferences"]):
            return {"pr_number": str(pr["number"]), "head_ref": pr["headRefName"]}
    return {"pr_number": "", "head_ref": ""}


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.gh_query")
    parser.add_argument("repo")
    parser.add_argument("query", choices=["head-ref", "head-sha", "closing-issue", "pr-for-issue"])
    parser.add_argument("number", type=int)
    args = parser.parse_args(argv)

    if args.query == "pr-for-issue":
        for key, value in pr_for_issue(args.repo, args.number).items():
            print(f"{key}={value}")
        return 0
    handlers = {
        "head-ref": head_ref,
        "head-sha": head_sha,
        "closing-issue": closing_issue,
    }
    print(handlers[args.query](args.repo, args.number))
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(_main))
