"""Single Actions entrypoint: builds ActionsCtx once and dispatches to pipeline commands."""

from __future__ import annotations

import sys

from . import cli
from . import (
    append_metrics,
    apply_verdict,
    check_review_cap,
    derive_code_hints,
    extract_metrics,
    fetch_issue,
    flag_failure,
    gather_fix_feedback,
    gate_issue_type,
    gh_query,
    handle_giveup,
    handle_pr_closed,
    handoff_to_review,
    labels,
    preserve_issue_body,
    report_run,
    route_red_checks,
    run_summary,
    safety_checks,
    spike_advisory,
    sync_labels,
    verdict,
    wait_for_checks,
)
from .ctx import ActionsCtx

_COMMANDS: dict[str, object] = {
    "fetch-issue": fetch_issue._main,
    "report-run": report_run._main,
    "flag-failure": flag_failure._main,
    "extract-metrics": extract_metrics._main,
    "append-metrics": append_metrics._main,
    "apply-verdict": apply_verdict._main,
    "check-review-cap": check_review_cap._main,
    "derive-code-hints": derive_code_hints._main,
    "gate-issue-type": gate_issue_type._main,
    "gather-fix-feedback": gather_fix_feedback._main,
    "gh-query": gh_query._main,
    "handle-giveup": handle_giveup._main,
    "handle-pr-closed": handle_pr_closed._main,
    "handoff-to-review": handoff_to_review._main,
    "labels": labels._main,
    "run-summary": run_summary._main,
    "route-red-checks": route_red_checks._main,
    "safety-checks": safety_checks._main,
    "spike-advisory": spike_advisory._main,
    "sync-labels": sync_labels._main,
    "wait-for-checks": wait_for_checks._main,
    "preserve-issue-body": preserve_issue_body._main,
    "verdict": verdict._main,
}


def main(argv: list[str]) -> int:
    if not argv:
        print("error: no command given", file=sys.stderr)
        print(f"available commands: {' '.join(sorted(_COMMANDS))}", file=sys.stderr)
        return 2

    command = argv[0]
    rest = argv[1:]

    if command not in _COMMANDS:
        print(f"error: unknown command: {command}", file=sys.stderr)
        print(f"available commands: {' '.join(sorted(_COMMANDS))}", file=sys.stderr)
        return 2

    try:
        ctx = ActionsCtx.from_env()
        if command == "safety-checks":
            return safety_checks._main(ctx, rest)
        return _COMMANDS[command](ctx, rest)
    except cli.MissingEnvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
