"""Reviewer check gate: block until every check on the PR has finished, then
report ok (and a reason when not ok). A red check routes the PR to a human
with no coder retry (#133); only the PR is escalated, the issue keeps its
status because the work is in a PR awaiting a human (#289).

Two things are excluded from the wait: this workflow run's own checks (they
never finish before the gate does) and anything in `checks.ignore` in
.github/interns.yml (non-blocking advisory checks).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from .. import gh
from . import lifecycle, lifecycle_apply


@dataclass(frozen=True)
class CheckSummary:
    total: int
    red: list[str]
    pending: list[str]


def classify(checks: list[dict], run_id: str, ignore: list[str]) -> CheckSummary:
    own_run = f"/runs/{run_id}/" if run_id else None
    relevant = [
        c for c in checks
        if not (own_run and own_run in (c.get("link") or ""))
        and c.get("name") not in ignore
    ]
    red = [f"{c['name']}={c['bucket']}" for c in relevant if c["bucket"] in ("fail", "cancel")]
    pending = [c["name"] for c in relevant if c["bucket"] == "pending"]
    return CheckSummary(total=len(relevant), red=red, pending=pending)


def wait_for_checks(
    repo: str, pr: int, run_id: str, ignore: list[str], *,
    timeout: float, poll: float, settle: float,
    sleep=time.sleep, monotonic=time.monotonic,
) -> tuple[bool, str]:
    start = monotonic()
    deadline = start + timeout
    last_pending: list[str] = []

    while True:
        now = monotonic()
        summary = classify(gh.pr_checks(repo, pr), run_id, ignore)
        last_pending = summary.pending
        print(f"checks: total={summary.total} red=[{', '.join(summary.red)}] pending={len(summary.pending)}")

        if summary.red:
            return False, f"red checks: {', '.join(summary.red)}"
        if summary.total == 0 and now - start >= settle:
            print("No checks reported on this PR — nothing to wait on.")
            return True, ""
        if summary.total > 0 and not summary.pending:
            return True, ""
        if now >= deadline:
            break
        sleep(poll)

    return False, f"timed out waiting for checks to finish: {', '.join(last_pending) or 'unknown'}"


def route_red_checks(repo: str, pr: int, reason: str, *, run_url: str) -> None:
    outcome = lifecycle.decide(lifecycle.Event.RED_CHECKS, lifecycle.Facts(has_issue=False, has_pr=True))
    lifecycle_apply.apply(repo, outcome, pr=pr, issue=None, words=lifecycle_apply.Words(run_url=run_url, detail=reason))
