"""Writes a Markdown run summary to $GITHUB_STEP_SUMMARY so the Actions run page
shows what an agent phase did without opening the step log.

Best-effort: the caller runs it with `if: always()`, so it must land even when the
Claude step failed or a `gh` lookup is rate-limited; lookups fall back to a plain line.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import ClassVar

from .. import best_effort, cli, execution, gh
from ..ctx import ActionsCtx
from ..domain import labels, verdict
from ..domain.verdict import ReviewState
from ..env_spec import EnvSpec


class Phase(StrEnum):
    CODER = "Coder"
    REVIEW = "Review"
    REFINEMENT = "Refinement"
    ESTIMATION = "Estimation"


class Round(StrEnum):
    INITIAL = "initial"
    FIX = "fix"


@dataclass(frozen=True)
class RunInfo:
    repo: str
    server_url: str
    run_url: str
    cost_warn: float | None


@dataclass(frozen=True)
class CoderRun:
    phase: ClassVar[Phase] = Phase.CODER
    issue: int
    pr: int | None
    round_: Round | None


@dataclass(frozen=True)
class ReviewRun:
    phase: ClassVar[Phase] = Phase.REVIEW
    pr: int
    reviewer_bot: str


@dataclass(frozen=True)
class RefinementRun:
    phase: ClassVar[Phase] = Phase.REFINEMENT
    issue: int


@dataclass(frozen=True)
class EstimationRun:
    phase: ClassVar[Phase] = Phase.ESTIMATION
    issue: int


PhaseRun = CoderRun | ReviewRun | RefinementRun | EstimationRun


@dataclass(frozen=True)
class FixState:
    """CHANGES_REQUESTED reviews seen on the PR; both None when the review list can't be fetched."""

    count: int | None
    last_flagged_sha: str | None


def _issue_title(repo: str, issue: int) -> str | None:
    data = best_effort.call("issue title lookup", gh.GhCommandError, gh.issue_view, repo, issue, ["title"])
    return data["title"] if data is not None else None


def _pr_title(repo: str, pr: int) -> str | None:
    data = best_effort.call("PR title lookup", gh.GhCommandError, gh.pr_view, repo, pr, ["title"])
    return data["title"] if data is not None else None


def _pr_head_sha(repo: str, pr: int) -> str | None:
    data = best_effort.call("PR head SHA lookup", gh.GhCommandError, gh.pr_view, repo, pr, ["headRefOid"])
    return data["headRefOid"] if data is not None else None


def _issue_labels(repo: str, issue: int) -> list[str] | None:
    return best_effort.call("issue labels lookup", gh.GhCommandError, labels.issue_labels, repo, issue)


def _pr_diff_file_count(repo: str, pr: int) -> int | None:
    names = best_effort.call("PR diff file names", gh.GhCommandError, gh.pr_diff_names, repo, pr)
    return len(names) if names is not None else None


def _coder_fix_state(repo: str, pr: int) -> FixState:
    """Counts CHANGES_REQUESTED from any reviewer, not just REVIEWER_BOT -- a
    human can also request changes."""
    reviews = best_effort.call("coder fix reviews", gh.GhCommandError, verdict.all_reviews, repo, pr)
    if reviews is None:
        return FixState(None, None)
    changes_requested = [r for r in reviews if r.state == ReviewState.CHANGES_REQUESTED]
    last_sha = changes_requested[-1].commit_id if changes_requested else None
    return FixState(len(changes_requested), last_sha)


def _reviewer_reviews(repo: str, pr: int, reviewer_bot: str) -> Sequence[verdict.Review] | None:
    return best_effort.call(
        "reviewer reviews lookup",
        gh.GhCommandError,
        verdict.reviews_by,
        repo, pr, reviewer_bot,
    )


def _round_line(round_: Round | None, fix_count: int | None) -> str | None:
    if round_ is Round.FIX:
        return f"Fix round {fix_count}" if fix_count is not None else "Fix round"
    if round_ is Round.INITIAL:
        return "Initial implementation"
    return None


def _quote_final_message(final_msg: str | None) -> list[str]:
    if not final_msg:
        return ["> _No final message — the run produced no result output._"]
    return [f"> {line}" for line in final_msg.splitlines()]


def _titled(label: str, link: str, title: str | None) -> str:
    return f"**{label}:** {link}" + (f" — {title}" if title else "")


def _issue_line(info: RunInfo, issue: int) -> str:
    link = f"[#{issue}]({info.server_url}/{info.repo}/issues/{issue})"
    return _titled("Issue", link, _issue_title(info.repo, issue))


def _outcome_line(info: RunInfo, pr: int | None, round_: Round | None, head_sha: str | None, last_flagged_sha: str | None) -> str:
    # `pr` only resolves an already-open PR -- for a fix round it says
    # nothing about whether this run pushed anything. Treat it as "updated"
    # only when the head has moved off the commit the reviewer flagged.
    if pr is None:
        return "**Outcome:** ⚠️ No PR — see the final message below."
    link = f"[#{pr}]({info.server_url}/{info.repo}/pull/{pr})"
    if round_ is not Round.FIX:
        return f"**Outcome:** PR opened — {link}"
    if head_sha and last_flagged_sha and head_sha != last_flagged_sha:
        return f"**Outcome:** PR updated — {link}"
    return "**Outcome:** ⚠️ No new commit pushed — see the final message below."


def _coder_section(info: RunInfo, run: CoderRun) -> list[str]:
    lines = [_issue_line(info, run.issue)]

    fix_state = FixState(None, None)
    if run.round_ is Round.FIX and run.pr is not None:
        fix_state = _coder_fix_state(info.repo, run.pr)
    round_line = _round_line(run.round_, fix_state.count)
    if round_line:
        lines.append(f"**Round:** {round_line}")

    head_sha = _pr_head_sha(info.repo, run.pr) if run.round_ is Round.FIX and run.pr is not None else None
    lines.append(_outcome_line(info, run.pr, run.round_, head_sha, fix_state.last_flagged_sha))

    if run.pr is not None:
        count = _pr_diff_file_count(info.repo, run.pr)
        lines.append(f"**Files changed:** {count if count is not None else 'unknown'}")

    return lines


def _verdict_outcome(last_state: ReviewState | None) -> str:
    match last_state:
        case ReviewState.APPROVED:
            return "**Outcome:** ✅ Approved"
        case ReviewState.CHANGES_REQUESTED:
            return "**Outcome:** 🔴 Changes requested"
        case _:
            return "**Outcome:** ⚠️ No verdict submitted — see the final message below."


def _review_section(info: RunInfo, run: ReviewRun) -> list[str]:
    pr_link = f"[#{run.pr}]({info.server_url}/{info.repo}/pull/{run.pr})"
    lines = [_titled("PR", pr_link, _pr_title(info.repo, run.pr))]

    # This run's own verdict is already posted by the time we get here, so
    # count only CHANGES_REQUESTED reviews against *earlier* commits -- a
    # review against the current head is this run's and isn't a prior round.
    head_sha = _pr_head_sha(info.repo, run.pr)
    reviews = _reviewer_reviews(info.repo, run.pr, run.reviewer_bot)
    if reviews is None:
        lines.append("**Round:** unavailable")
        lines.append("**Outcome:** ⚠️ Review lookup failed — see the step log.")
        return lines
    rc_count = verdict.rounds_requested(reviews, exclude_commit=head_sha)
    if rc_count > 0:
        lines.append(f"**Round:** re-review (after {rc_count} changes-requested)")
    else:
        lines.append("**Round:** initial review")

    # A verdict is this run's outcome only if it was submitted against the
    # PR's current head -- otherwise it's a stale review from an earlier
    # round and this run submitted nothing.
    lines.append(_verdict_outcome(verdict.verdict_for_head(reviews, head_sha or "")))
    return lines


def _issue_label_section(info: RunInfo, issue: int, outcome_for: Callable[[list[str]], str]) -> list[str]:
    lines = [_issue_line(info, issue)]
    current_labels = _issue_labels(info.repo, issue)
    if current_labels is None:
        lines.append("**Outcome:** ⚠️ Label lookup failed — see the step log.")
    else:
        lines.append(outcome_for(current_labels))
    return lines


def _refinement_outcome(current_labels: list[str]) -> str:
    if labels.STATUS_REFINED in current_labels:
        return "**Outcome:** Body refined"
    if labels.STATUS_NEEDS_ATTENTION in current_labels:
        return "**Outcome:** ⚠️ Stopped for clarification — see the final message below."
    return "**Outcome:** ⚠️ Ended without a terminal state — see the final message below."


def _estimation_outcome(current_labels: list[str]) -> str:
    size = labels.find_size_label(current_labels)
    if size:
        return f"**Outcome:** Estimate posted — `{size}`"
    if labels.STATUS_NEEDS_ATTENTION in current_labels:
        return "**Outcome:** ⚠️ Stopped for clarification — see the final message below."
    return "**Outcome:** ⚠️ Ended without an estimate — see the final message below."


def _section(info: RunInfo, run: PhaseRun) -> list[str]:
    match run:
        case CoderRun():
            return _coder_section(info, run)
        case ReviewRun():
            return _review_section(info, run)
        case RefinementRun():
            return _issue_label_section(info, run.issue, _refinement_outcome)
        case EstimationRun():
            return _issue_label_section(info, run.issue, _estimation_outcome)


def _execution_file_written(exec_file: str | None) -> bool:
    return exec_file is not None and Path(exec_file).is_file()


def build_summary(info: RunInfo, run: PhaseRun, exec_file: str | None) -> str:
    _result = execution.result_entry(exec_file)

    def _field(key: str) -> str | None:
        v = _result.get(key) if _result else None
        return str(v) if v not in (None, "") else None

    raw_cost  = _field("total_cost_usd")
    num_turns = _field("num_turns")
    final_msg = _field("result")

    lines = [f"## {run.phase} run", ""]
    lines += _section(info, run)

    if not _execution_file_written(exec_file):
        lines += ["", "> _No execution file — the agent step was killed (timed out) before writing results._"]

    cost_line = f"**Cost:** ${execution.format_cost(raw_cost)}"
    if num_turns:
        cost_line += f" · {num_turns} turns"
    lines.append(cost_line)

    if raw_cost and info.cost_warn is not None and float(raw_cost) > info.cost_warn:
        lines += ["", f"⚠️ cost ${execution.format_cost(raw_cost)} over the ${info.cost_warn:.2f} warn limit"]

    lines += [f"[Full run log]({info.run_url})", "", "### Agent's final message", ""]
    lines += _quote_final_message(final_msg)

    return "\n".join(lines) + "\n"


def _parse_phase(raw: str) -> Phase:
    try:
        return Phase(raw)
    except ValueError:
        raise ValueError(f"run-summary: unknown phase {raw}") from None


def _required(value: int | None, flag: str, phase: Phase) -> int:
    if value is None:
        raise ValueError(f"run-summary: {flag} is required for the {phase} phase")
    return value


def _phase_run(phase: Phase, issue: int | None, pr: int | None, round_: Round | None, ctx: ActionsCtx) -> PhaseRun:
    match phase:
        case Phase.CODER:
            return CoderRun(_required(issue, "--issue", phase), pr, round_)
        case Phase.REVIEW:
            return ReviewRun(_required(pr, "--pr", phase), ctx.reviewer_bot)
        case Phase.REFINEMENT:
            return RefinementRun(_required(issue, "--issue", phase))
        case Phase.ESTIMATION:
            return EstimationRun(_required(issue, "--issue", phase))


def _phase_of(argv: list[str]) -> list[str]:
    parser = cli.build_parser("run-summary")
    parser.add_argument("--phase", required=True)
    args, _ = parser.parse_known_args(argv)
    return [args.phase]


ENV_SPEC = EnvSpec(
    always=frozenset({"GITHUB_RUN_ID", "GITHUB_STEP_SUMMARY"}),
    by_phase={Phase.REVIEW.value: frozenset({"REVIEWER_BOT"})},
    phases=_phase_of,
)


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("run-summary")
    parser.add_argument("--phase", required=True)
    parser.add_argument("--exec-file", default="")
    parser.add_argument("--issue", default="")
    parser.add_argument("--pr", default="")
    parser.add_argument("--round", dest="round_", type=Round, choices=list(Round), default=None)
    parser.add_argument("--cost-warn", dest="cost_warn", default="")
    args = parser.parse_args(argv)

    summary_path = ctx.step_summary
    phase = _parse_phase(args.phase)
    run = _phase_run(phase, cli.optional_int(args.issue), cli.optional_int(args.pr), args.round_, ctx)
    info = RunInfo(ctx.repo, ctx.server_url, ctx.run_url(), float(args.cost_warn) if args.cost_warn else None)
    summary = build_summary(info, run, args.exec_file or None)
    with open(summary_path, "a") as f:
        f.write(summary)
    return 0
