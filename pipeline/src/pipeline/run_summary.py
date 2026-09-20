"""Writes a Markdown run summary to $GITHUB_STEP_SUMMARY so the Actions run
page shows what an agent phase did without opening the turn-by-turn step
log. Complements report_run.py: same cost figure, but richer detail and on
the run page only, never the ticket.

Best-effort -- never raises on a `gh` lookup failure. The caller runs this
with `if: always()`, so a summary should land even when the Claude step
itself failed or a `gh` call is rate-limited; every lookup below falls back
to a plain line instead.
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import execution, gh, labels, report_run, verdict


def _issue_title(repo: str, issue: str) -> str:
    try:
        return gh.issue_view(repo, int(issue), ["title"])["title"]
    except gh.GhCommandError:
        return ""


def _pr_title(repo: str, pr: str) -> str:
    try:
        return gh.pr_view(repo, int(pr), ["title"])["title"]
    except gh.GhCommandError:
        return ""


def _pr_head_sha(repo: str, pr: str) -> str:
    try:
        return gh.pr_view(repo, int(pr), ["headRefOid"])["headRefOid"]
    except gh.GhCommandError:
        return ""


def _issue_labels(repo: str, issue: str) -> list[str]:
    try:
        return labels.issue_labels(repo, int(issue))
    except gh.GhCommandError:
        return []


def _pr_diff_file_count(repo: str, pr: str) -> int | None:
    try:
        return len(gh.pr_diff_names(repo, int(pr)))
    except gh.GhCommandError:
        return None


def _coder_fix_state(repo: str, pr: str) -> tuple[str, str]:
    """(fix_n, last_flagged_sha) for the coder-phase round line and outcome
    check. Counts CHANGES_REQUESTED from any reviewer, not just
    REVIEWER_BOT -- a human can also request changes. ("", "") when the
    review list can't be fetched."""
    try:
        reviews = verdict.all_reviews(repo, int(pr))
    except gh.GhCommandError:
        return "", ""
    changes_requested = [r for r in reviews if r.state == "CHANGES_REQUESTED"]
    last_sha = changes_requested[-1].commit_id if changes_requested else ""
    return str(len(changes_requested)), last_sha


def _reviewer_reviews(repo: str, pr: str, reviewer_bot: str) -> list[verdict.Review]:
    try:
        return verdict.reviews_by(repo, int(pr), reviewer_bot)
    except gh.GhCommandError:
        return []


def _round_line(round_: str, fix_n: str) -> str:
    if round_ == "fix":
        return f"Fix round {fix_n}" if fix_n else "Fix round"
    if round_ == "initial":
        return "Initial implementation"
    return ""


def _quote_final_message(final_msg: str | None) -> list[str]:
    if not final_msg:
        return ["> _No final message — the run produced no result output._"]
    return [f"> {line}" for line in final_msg.splitlines()]


def _coder_section(repo: str, server_url: str, issue: str, pr: str, round_: str) -> list[str]:
    lines = []
    title = _issue_title(repo, issue)
    lines.append(f"**Issue:** [#{issue}]({server_url}/{repo}/issues/{issue})" + (f" — {title}" if title else ""))

    fix_n, last_flagged_sha = ("", "")
    if round_ == "fix" and pr:
        fix_n, last_flagged_sha = _coder_fix_state(repo, pr)
    round_line = _round_line(round_, fix_n)
    if round_line:
        lines.append(f"**Round:** {round_line}")

    # `pr` only resolves an already-open PR -- for a fix round it says
    # nothing about whether this run pushed anything. Treat it as "updated"
    # only when the head has moved off the commit the reviewer flagged;
    # otherwise the run failed silently after the PR already existed.
    if not pr:
        lines.append("**Outcome:** ⚠️ No PR — see the final message below.")
    elif round_ == "fix":
        head_sha = _pr_head_sha(repo, pr)
        if head_sha and last_flagged_sha and head_sha != last_flagged_sha:
            lines.append(f"**Outcome:** PR updated — [#{pr}]({server_url}/{repo}/pull/{pr})")
        else:
            lines.append("**Outcome:** ⚠️ No new commit pushed — see the final message below.")
    else:
        lines.append(f"**Outcome:** PR opened — [#{pr}]({server_url}/{repo}/pull/{pr})")

    if pr:
        count = _pr_diff_file_count(repo, pr)
        lines.append(f"**Files changed:** {count if count is not None else 'unknown'}")

    return lines


def _review_section(repo: str, server_url: str, pr: str, reviewer_bot: str) -> list[str]:
    lines = []
    title = _pr_title(repo, pr)
    lines.append(f"**PR:** [#{pr}]({server_url}/{repo}/pull/{pr})" + (f" — {title}" if title else ""))

    # This run's own verdict is already posted by the time we get here, so
    # count only CHANGES_REQUESTED reviews against *earlier* commits -- a
    # review against the current head is this run's and isn't a prior round.
    head_sha = _pr_head_sha(repo, pr)
    reviews = _reviewer_reviews(repo, pr, reviewer_bot)
    rc_count = verdict.rounds_requested(reviews, exclude_commit=head_sha)
    if rc_count > 0:
        lines.append(f"**Round:** re-review (after {rc_count} changes-requested)")
    else:
        lines.append("**Round:** initial review")

    # A verdict is this run's outcome only if it was submitted against the
    # PR's current head -- otherwise it's a stale review from an earlier
    # round and this run submitted nothing.
    last_state = verdict.verdict_for_head(reviews, head_sha)
    if last_state == "APPROVED":
        lines.append("**Outcome:** ✅ Approved")
    elif last_state == "CHANGES_REQUESTED":
        lines.append("**Outcome:** 🔴 Changes requested")
    else:
        lines.append("**Outcome:** ⚠️ No verdict submitted — see the final message below.")

    return lines


def _refinement_section(repo: str, server_url: str, issue: str) -> list[str]:
    lines = []
    title = _issue_title(repo, issue)
    lines.append(f"**Issue:** [#{issue}]({server_url}/{repo}/issues/{issue})" + (f" — {title}" if title else ""))

    current_labels = _issue_labels(repo, issue)
    if "status:refined" in current_labels:
        lines.append("**Outcome:** Body refined")
    elif "status:needs-attention" in current_labels:
        lines.append("**Outcome:** ⚠️ Stopped for clarification — see the final message below.")
    else:
        lines.append("**Outcome:** ⚠️ Ended without a terminal state — see the final message below.")

    return lines


def _estimation_section(repo: str, server_url: str, issue: str) -> list[str]:
    lines = []
    title = _issue_title(repo, issue)
    lines.append(f"**Issue:** [#{issue}]({server_url}/{repo}/issues/{issue})" + (f" — {title}" if title else ""))

    current_labels = _issue_labels(repo, issue)
    size = next((label for label in current_labels if label.startswith("size:")), None)
    if size:
        lines.append(f"**Outcome:** Estimate posted — `{size}`")
    elif "status:needs-attention" in current_labels:
        lines.append("**Outcome:** ⚠️ Stopped for clarification — see the final message below.")
    else:
        lines.append("**Outcome:** ⚠️ Ended without an estimate — see the final message below.")

    return lines


def _execution_file_written(exec_file: str | None) -> bool:
    return exec_file is not None and Path(exec_file).is_file()


def build_summary(repo: str, server_url: str, phase: str, exec_file: str | None, *,
                   issue: str = "", pr: str = "", round_: str = "", cost_warn: str = "",
                   reviewer_bot: str = "") -> str:
    raw_cost = execution.result_field(exec_file, "total_cost_usd")
    num_turns = execution.result_field(exec_file, "num_turns")
    final_msg = execution.result_field(exec_file, "result")

    lines = [f"## {phase} run", ""]

    if phase == "Coder":
        lines += _coder_section(repo, server_url, issue, pr, round_)
    elif phase == "Review":
        lines += _review_section(repo, server_url, pr, reviewer_bot)
    elif phase == "Refinement":
        lines += _refinement_section(repo, server_url, issue)
    elif phase == "Estimation":
        lines += _estimation_section(repo, server_url, issue)
    else:
        raise ValueError(f"run-summary: unknown phase {phase}")

    if not _execution_file_written(exec_file):
        lines += ["", "> _No execution file — the agent step was killed (timed out) before writing results._"]

    cost_line = f"**Cost:** ${report_run.format_cost(raw_cost)}"
    if num_turns:
        cost_line += f" · {num_turns} turns"
    lines.append(cost_line)

    if raw_cost and cost_warn and float(raw_cost) > float(cost_warn):
        lines += ["", f"⚠️ cost ${report_run.format_cost(raw_cost)} over the ${float(cost_warn):.2f} warn limit"]

    lines += [f"[Full run log]({gh.run_url(repo)})", "", "### Agent's final message", ""]
    lines += _quote_final_message(final_msg)

    return "\n".join(lines) + "\n"


def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="python -m pipeline.run_summary")
    parser.add_argument("phase")
    parser.add_argument("exec_file", nargs="?", default="")
    parser.add_argument("--issue", default="")
    parser.add_argument("--pr", default="")
    parser.add_argument("--round", dest="round_", default="")
    parser.add_argument("--cost-warn", dest="cost_warn", default="")
    args = parser.parse_args(argv)

    repo = os.environ["GITHUB_REPOSITORY"]
    server_url = os.environ["GITHUB_SERVER_URL"]
    summary_path = os.environ["GITHUB_STEP_SUMMARY"]
    reviewer_bot = os.environ.get("REVIEWER_BOT", "")

    summary = build_summary(
        repo, server_url, args.phase, args.exec_file or None,
        issue=args.issue, pr=args.pr, round_=args.round_, cost_warn=args.cost_warn,
        reviewer_bot=reviewer_bot,
    )
    with open(summary_path, "a") as f:
        f.write(summary)
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
