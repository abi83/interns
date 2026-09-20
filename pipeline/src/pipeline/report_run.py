"""Posts the "<Phase> [pipeline run](url) -- cost: $X" comment every agent
phase drops on the ticket. Cost tracking lives on the issue (refine,
estimate, coder and reviewer all post there) so spend aggregates from one
place. Cost is parsed from the claude-code-action execution file; "unknown"
when the run produced none.
"""

from __future__ import annotations

import sys

from . import execution, gh


def format_cost(raw: str | None) -> str:
    return f"{float(raw):.4f}" if raw else "unknown"


def report(repo: str, phase: str, exec_file: str | None, issue: int | None,
           pr: int | None, warn: str | None) -> None:
    raw_cost = execution.result_field(exec_file, "total_cost_usd")
    body = f"{phase} [pipeline run]({gh.run_url(repo)}) — cost: ${format_cost(raw_cost)}"
    if warn:
        body += f"\n\n⚠️ {warn}"

    if issue is not None:
        gh.issue_comment(repo, issue, body)
    elif pr is not None:
        gh.pr_comment(repo, pr, body)
    else:
        raise ValueError("report-run: need an issue or PR number")


def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="python -m pipeline.report_run")
    parser.add_argument("phase")
    parser.add_argument("exec_file")
    parser.add_argument("issue", nargs="?", default="")
    parser.add_argument("pr", nargs="?", default="")
    parser.add_argument("--warn", default=None)
    args = parser.parse_args(argv)

    report(
        os.environ["GITHUB_REPOSITORY"],
        args.phase,
        args.exec_file,
        int(args.issue) if args.issue else None,
        int(args.pr) if args.pr else None,
        args.warn,
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
