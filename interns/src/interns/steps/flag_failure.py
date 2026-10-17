"""Common failure handler for the agent phases: fires the job-crashed
lifecycle event with the failure details gathered from the execution log."""

from __future__ import annotations

from collections import Counter
from enum import StrEnum
from pathlib import Path

from .. import cli, execution
from ..ctx import ActionsCtx
from ..domain import lifecycle, lifecycle_apply
from ..env_spec import EnvSpec

ENV_SPEC = EnvSpec.of("GITHUB_RUN_ID")


class Noun(StrEnum):
    REFINEMENT = "refinement"
    ESTIMATION = "estimation"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"


MAX_LISTED_DENIALS = 5
MAX_COMMAND_CHARS = 80
# A SIGKILLed run (job timeout) leaves a log without a result entry.
NO_RESULT_NOTE = "Agent stopped: no result was recorded (the run was likely killed, e.g. on timeout)."


def _denial_label(denial: dict) -> str:
    tool_input = denial.get("tool_input") or {}
    text = tool_input.get("command") or tool_input.get("file_path") or denial["tool_name"]
    text = " ".join(str(text).split()).replace("`", "'")
    return text if len(text) <= MAX_COMMAND_CHARS else text[: MAX_COMMAND_CHARS - 1] + "…"


def _stop_reason(entry: dict) -> str | None:
    if entry.get("subtype") != "success":
        return "; ".join(entry.get("errors") or []) or entry.get("subtype") or "unknown"
    if entry.get("is_error"):
        return entry.get("result") or entry.get("api_error") or "the agent reported an error"
    return None


def _denial_lines(entry: dict) -> list[str]:
    denials = execution.permission_denials(entry)
    if not denials:
        return []
    lines = [f"{len(denials)} tool calls were denied:"]
    ranked = Counter(_denial_label(d) for d in denials).most_common()
    for label, count in ranked[:MAX_LISTED_DENIALS]:
        lines.append(f"- `{label}`" + (f" (×{count})" if count > 1 else ""))
    hidden = sum(count for _, count in ranked[MAX_LISTED_DENIALS:])
    if hidden:
        lines.append(f"- and {hidden} more")
    return lines


def failure_details(exec_file: str) -> str:
    """Why the agent stopped, then which tool calls were denied, from the
    execution log. Empty when there is no usable log."""
    entry = execution.result_entry(exec_file)
    if entry is None:
        return NO_RESULT_NOTE if Path(exec_file).is_file() else ""
    lines = []
    reason = _stop_reason(entry)
    if reason:
        lines.append(f"Agent stopped: {reason.rstrip('.')}.")
    # An API error (e.g. the session limit) ends the run no matter what was denied earlier.
    if not entry.get("api_error"):
        lines.extend(_denial_lines(entry))
    return "\n".join(lines)


def flag_failure(repo: str, noun: Noun, issue: int | None, pr: int | None, fix_round: bool, *,
                 run_url: str = "", exec_file: str = "", draft_pr_url: str = "") -> None:
    details = failure_details(exec_file)
    suffix = f"\n\n{details}" if details else ""
    if draft_pr_url:
        suffix += f"\n\nDraft PR with the unfinished work: {draft_pr_url}"
    if issue is None and pr is None:
        raise ValueError("one of --issue or --pr is required")
    event = lifecycle.Event.JOB_CRASHED_FIX_ROUND if fix_round else lifecycle.Event.JOB_CRASHED
    outcome = lifecycle.decide(event, lifecycle.Facts(has_issue=issue is not None, has_pr=pr is not None))
    words = lifecycle_apply.Words(run_url=run_url, detail=suffix, noun=noun)
    lifecycle_apply.apply(repo, outcome, pr=pr, issue=issue, words=words)


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("flag-failure")
    parser.add_argument("--noun", type=Noun, choices=list(Noun), required=True)
    parser.add_argument("--issue", default="")
    parser.add_argument("--pr", default="")
    parser.add_argument("--fix-round", action="store_true")
    parser.add_argument("--exec-file", default="")
    parser.add_argument("--draft-pr-url", default="")
    args = parser.parse_args(argv)

    flag_failure(
        ctx.repo,
        args.noun,
        cli.optional_int(args.issue),
        cli.optional_int(args.pr),
        args.fix_round,
        run_url=ctx.run_url(),
        exec_file=args.exec_file,
        draft_pr_url=args.draft_pr_url,
    )
    return 0
