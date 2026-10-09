"""Common failure handler for the agent phases: send the issue to
status:needs-attention, mark the PR pr:needs-attention (or just clear its
label on a fix-round crash, which escalates issue-side), and post a comment
linking the run.
"""

from __future__ import annotations

from collections import Counter

from .. import cli, execution, gh
from . import labels
from ..ctx import ActionsCtx


MAX_LISTED_DENIALS = 5
MAX_COMMAND_CHARS = 80


def _denial_label(denial: dict) -> str:
    tool_input = denial.get("tool_input") or {}
    text = tool_input.get("command") or tool_input.get("file_path") or denial["tool_name"]
    text = " ".join(str(text).split()).replace("`", "'")
    return text if len(text) <= MAX_COMMAND_CHARS else text[: MAX_COMMAND_CHARS - 1] + "…"


def failure_details(exec_file: str) -> str:
    """Why the agent stopped and which tool calls were denied, from the
    execution log. Empty when there is no usable log."""
    entry = execution.result_entry(exec_file)
    if entry is None:
        return ""
    lines = []
    if entry.get("subtype") != "success":
        reason = "; ".join(entry.get("errors") or []) or entry.get("subtype") or "unknown"
        lines.append(f"Agent stopped: {reason}.")
    denials = execution.permission_denials(entry)
    if denials:
        lines.append(f"{len(denials)} tool calls were denied:")
        ranked = Counter(_denial_label(d) for d in denials).most_common()
        for label, count in ranked[:MAX_LISTED_DENIALS]:
            lines.append(f"- `{label}`" + (f" (×{count})" if count > 1 else ""))
        hidden = sum(count for _, count in ranked[MAX_LISTED_DENIALS:])
        if hidden:
            lines.append(f"- and {hidden} more")
    return "\n".join(lines)


def flag_failure(repo: str, noun: str, issue: int | None, pr: int | None, fix_round: bool, *,
                 run_url: str = "", exec_file: str = "") -> None:
    details = failure_details(exec_file)
    suffix = f"\n\n{details}" if details else ""
    # A review-job crash leaves the PR stuck with no verdict; mark it for a
    # human. A fix-round crash escalates on the issue side, so the PR just
    # loses its label.
    if pr is not None:
        if fix_round:
            labels.set_pr_pipeline_label(repo, pr)
        else:
            labels.escalate_pr(repo, pr)
    if issue is not None:
        labels.set_issue_status(repo, issue, labels.STATUS_NEEDS_ATTENTION)

    if fix_round:
        if issue is None:
            raise ValueError("--fix-round requires --issue")
        gh.issue_comment(
            repo, issue,
            "Automated fix round failed — issue set to `status:needs-attention`. "
            f"Re-dispatch once the cause is addressed: `gh workflow run code-pipeline.yml "
            f"-f phase=coder -f issue_number={issue} -f fix_round=true`. Run: {run_url}{suffix}",
        )
        return

    body = f"Automated {noun} failed. See the run: {run_url}{suffix}"
    if pr is not None:
        gh.pr_comment(repo, pr, body)
    else:
        if issue is None:
            raise ValueError("one of --issue or --pr is required")
        gh.issue_comment(repo, issue, body)


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="interns.entrypoint flag-failure")
    parser.add_argument("--noun", default="")
    parser.add_argument("--issue", default="")
    parser.add_argument("--pr", default="")
    parser.add_argument("--fix-round", action="store_true")
    parser.add_argument("--exec-file", default="")
    args = parser.parse_args(argv)

    flag_failure(
        ctx.repo,
        args.noun,
        cli.optional_int(args.issue),
        cli.optional_int(args.pr),
        args.fix_round,
        run_url=ctx.run_url(),
        exec_file=args.exec_file,
    )
    return 0
