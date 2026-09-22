"""Reviewer gate: block until every check on the PR has finished, then
report ok (and a reason when not ok). A red check routes the PR to a human
with no coder retry; workflow_dispatch skips the gate.

Two things are excluded from the wait: this workflow run's own checks (they
never finish before the gate does) and anything in `checks.ignore` in
.github/interns.yml (non-blocking advisory checks), read via
pipeline.config -- the file's only reader. A malformed config now fails the
gate loudly instead of silently ignoring nothing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from . import cli, config, gh
from .ctx import ActionsCtx


@dataclass(frozen=True)
class CheckSummary:
    total: int
    red: list[str]
    pending: list[str]


def _classify(checks: list[dict], run_id: str, ignore: list[str]) -> CheckSummary:
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
    timeout: float = 1200, poll: float = 20, settle: float = 30,
    sleep=time.sleep, monotonic=time.monotonic,
) -> tuple[bool, str]:
    start = monotonic()
    deadline = start + timeout
    last_pending: list[str] = []

    while True:
        now = monotonic()
        summary = _classify(gh.pr_checks(repo, pr), run_id, ignore)
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


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="interns.entrypoint wait-for-checks")
    parser.add_argument("--pr", type=int, required=True)
    args = parser.parse_args(argv)

    if ctx.event_name == "workflow_dispatch":
        print("Manual dispatch — skipping the check gate.")
        cli.write_output("ok", True)
        return 0

    config_path = os.environ.get("INTERNS_CONFIG", ".github/interns.yml")
    ignore = config.checks_ignore(config.load_raw(config_path), config_path)

    ok, reason = wait_for_checks(
        ctx.repo, args.pr, ctx.run_id, ignore,
        timeout=float(os.environ.get("CHECK_TIMEOUT_SECONDS", "1200")),
        poll=float(os.environ.get("CHECK_POLL_SECONDS", "20")),
        settle=float(os.environ.get("CHECK_SETTLE_SECONDS", "30")),
    )
    cli.write_output("ok", ok)
    if not ok:
        cli.write_output("reason", reason)
    return 0
