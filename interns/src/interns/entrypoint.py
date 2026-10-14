"""Single Actions entrypoint: dispatches to commands with one missing-env error path.

Every registered command's `main` lives in a module under `steps/`. Commands
take `(ctx, argv)` with an ActionsCtx built once. The exception is
`_ENV_FREE_COMMANDS`, which take `(argv)` only."""

from __future__ import annotations

import inspect
import sys
from collections.abc import Callable

from . import cli
from .ctx import CTX_ENV, ActionsCtx
from .env_spec import EnvSpec
from .steps import (
    append_metrics,
    apply_verdict,
    auto_proceed,
    check_build_config,
    confirm_route,
    derive_code_hints,
    edit_labels,
    extract_metrics,
    fetch_issue,
    flag_failure,
    gather_fix_feedback,
    gh_query,
    handle_giveup,
    handle_pr_closed,
    handoff_to_review,
    preserve_issue_body,
    prompt,
    query_verdict,
    report_run,
    route_event,
    resolve_issue_template,
    run_agent,
    run_setup,
    run_summary,
    save_draft_pr,
    show_config,
    spike_advisory,
    sync_labels,
)

_Command = Callable[[ActionsCtx, list[str]], int]
_EnvFreeCommand = Callable[[list[str]], int]

_COMMANDS: dict[str, _Command] = {
    "fetch-issue": fetch_issue.main,
    "report-run": report_run.main,
    "flag-failure": flag_failure.main,
    "extract-metrics": extract_metrics.main,
    "append-metrics": append_metrics.main,
    "apply-verdict": apply_verdict.main,
    "auto-proceed": auto_proceed.main,
    "derive-code-hints": derive_code_hints.main,
    "gather-fix-feedback": gather_fix_feedback.main,
    "gh-query": gh_query.main,
    "handle-giveup": handle_giveup.main,
    "handle-pr-closed": handle_pr_closed.main,
    "handoff-to-review": handoff_to_review.main,
    "labels": edit_labels.main,
    "run-summary": run_summary.main,
    "save-draft-pr": save_draft_pr.main,
    "spike-advisory": spike_advisory.main,
    "sync-labels": sync_labels.main,
    "confirm-route": confirm_route.main,
    "route-event": route_event.main,
    "preserve-issue-body": preserve_issue_body.main,
    "verdict": query_verdict.main,
}

# Exception to the `(ctx, argv)` signature: these run in workflow steps that
# carry no GitHub token or repository env, and `ActionsCtx.from_env` requires
# them, so building a ctx would fail the step.
_ENV_FREE_COMMANDS: dict[str, _EnvFreeCommand] = {
    "check-build-config": check_build_config.main,
    "config": show_config.main,
    "prompt": prompt.main,
    "resolve-issue-template": resolve_issue_template.main,
    "run-agent": run_agent.main,
    "run-setup": run_setup.main,
}


def env_spec(command: str) -> EnvSpec:
    main = {**_COMMANDS, **_ENV_FREE_COMMANDS}[command]
    module = inspect.getmodule(main)
    if module is None:
        raise RuntimeError(f"no module for command {command}")
    return module.ENV_SPEC


def required_env(command: str, argv: list[str]) -> frozenset[str]:
    """Env a workflow step must supply for `command` run with `argv`."""
    base = frozenset() if command in _ENV_FREE_COMMANDS else CTX_ENV
    return base | env_spec(command).required(argv)


def _available() -> str:
    return " ".join(sorted([*_COMMANDS, *_ENV_FREE_COMMANDS]))


def _dispatch(command: str, rest: list[str]) -> int:
    if command in _ENV_FREE_COMMANDS:
        return _ENV_FREE_COMMANDS[command](rest)
    return _COMMANDS[command](ActionsCtx.from_env(), rest)


def main(argv: list[str]) -> int:
    if not argv:
        print("error: no command given", file=sys.stderr)
        print(f"available commands: {_available()}", file=sys.stderr)
        return 2

    command, rest = argv[0], argv[1:]
    if command not in _COMMANDS and command not in _ENV_FREE_COMMANDS:
        print(f"error: unknown command: {command}", file=sys.stderr)
        print(f"available commands: {_available()}", file=sys.stderr)
        return 2

    try:
        return _dispatch(command, rest)
    except cli.MissingEnvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
