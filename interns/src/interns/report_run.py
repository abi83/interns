"""Posts the "<Phase> [pipeline run](url) -- cost: $X" comment every agent
phase drops on the ticket. Cost tracking lives on the issue (refine,
estimate, coder and reviewer all post there) so spend aggregates from one
place. Cost is parsed from the claude-code-action execution file; "unknown"
when the run produced none.
"""

from __future__ import annotations


from . import cli, execution, gh
from .ctx import ActionsCtx


def format_cost(raw: str | None) -> str:
    return f"{float(raw):.4f}" if raw else "unknown"


def report(repo: str, phase: str, exec_file: str | None, issue: int | None,
           pr: int | None, warn: str | None, *, run_url: str = "") -> None:
    raw_cost = execution.result_field(exec_file, "total_cost_usd")
    body = f"{phase} [pipeline run]({run_url}) — cost: ${format_cost(raw_cost)}"
    if warn:
        body += f"\n\n⚠️ {warn}"

    if issue is not None:
        gh.issue_comment(repo, issue, body)
    elif pr is not None:
        gh.pr_comment(repo, pr, body)
    else:
        raise ValueError("report-run: need an issue or PR number")


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="interns.entrypoint report-run")
    parser.add_argument("--phase", required=True)
    parser.add_argument("--exec-file", required=True)
    parser.add_argument("--issue", default="")
    parser.add_argument("--pr", default="")
    parser.add_argument("--warn", default=None)
    args = parser.parse_args(argv)

    report(
        ctx.repo,
        args.phase,
        args.exec_file,
        cli.optional_int(args.issue),
        cli.optional_int(args.pr),
        args.warn,
        run_url=ctx.run_url(),
    )
    return 0
