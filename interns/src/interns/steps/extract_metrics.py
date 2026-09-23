"""Parses one claude-code-action execution file into a single
pipeline-metrics record (one JSON object), for append_metrics to persist.

Bump SCHEMA_VERSION and .github/pipeline-metrics.schema.json together on any
breaking shape change.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .. import cli, execution
from ..ctx import ActionsCtx

SCHEMA_VERSION = 2
JOBS = ("refiner", "estimator", "coder", "reviewer")


class NoResultEventError(RuntimeError):
    """The execution file has no `result` event -- a killed run can leave a
    truncated file."""


def _tool_calls(events: list[dict]) -> dict[str, int]:
    """Main-agent tool_use blocks only, grouped by name -- a sub-agent
    (isSidechain) invocation isn't a top-level pipeline action.

    Bash calls are sub-labelled: script basename for .sh invocations
    (e.g. Bash:comment-issue.sh), Bash:other for everything else."""
    counts: dict[str, int] = {}
    for event in events:
        if event.get("type") != "assistant" or event.get("isSidechain"):
            continue
        for block in event.get("message", {}).get("content") or []:
            if block.get("type") != "tool_use":
                continue
            name = block["name"]
            if name == "Bash":
                cmd = block.get("input", {}).get("command", "")
                sh = next((p for p in cmd.split() if p.endswith(".sh")), None)
                name = f"Bash:{Path(sh).name}" if sh else "Bash:other"
            counts[name] = counts.get(name, 0) + 1
    return counts


def _denied_tools(events: list[dict]) -> list[str]:
    """Distinct tool names denied by the permission system (main agent only).

    Denials appear as user-side tool_results with is_error=True whose content
    contains "denied"; we correlate back to the tool name via tool_use_id."""
    tool_use_names: dict[str, str] = {}
    denied: set[str] = set()
    for event in events:
        if event.get("type") == "assistant" and not event.get("isSidechain"):
            for block in event.get("message", {}).get("content") or []:
                if block.get("type") == "tool_use":
                    tool_use_names[block.get("id", "")] = block["name"]
        elif event.get("type") == "user":
            for block in event.get("message", {}).get("content") or []:
                if block.get("type") != "tool_result" or not block.get("is_error"):
                    continue
                content = block.get("content", "")
                text = content if isinstance(content, str) else ""
                if "denied" in text.lower():
                    tool_id = block.get("tool_use_id", "")
                    if tool_id in tool_use_names:
                        denied.add(tool_use_names[tool_id])
    return sorted(denied)


def _models(model_usage: dict) -> dict[str, dict]:
    return {
        name: {
            "input_tokens": usage.get("inputTokens", 0),
            "output_tokens": usage.get("outputTokens", 0),
            "cache_read_tokens": usage.get("cacheReadInputTokens", 0),
            "cache_creation_tokens": usage.get("cacheCreationInputTokens", 0),
            "cost_usd": usage.get("costUSD", 0),
        }
        for name, usage in model_usage.items()
    }


def build_record(exec_file: str, *, job: str, issue: int | None, pr: int | None,
                  repo: str, run_id: int, run_attempt: int, interns_ref: str) -> dict:
    try:
        evts = execution.events(exec_file)
    except json.JSONDecodeError as exc:
        # A killed run can leave a truncated (invalid-JSON) file -- treat it
        # the same as a well-formed file with no result event, matching the
        # bash version's `jq -e` failing the same way on either.
        raise NoResultEventError(f"no result event in {exec_file}") from exc
    results = [e for e in evts if e.get("type") == "result"]
    if not results:
        raise NoResultEventError(f"no result event in {exec_file}")
    result = results[-1]

    return {
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": repo,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "job": job,
        "issue": issue,
        "pr": pr,
        "interns_ref": interns_ref,
        "session_id": result.get("session_id"),
        "agent_result": result.get("subtype"),
        "num_turns": result.get("num_turns"),
        "duration_ms": result.get("duration_ms"),
        "duration_api_ms": result.get("duration_api_ms"),
        "models": _models(result.get("modelUsage") or {}),
        "tool_calls": _tool_calls(evts),
        "permission_denials": result.get("permission_denials_count") or 0,
        "denied_tools": _denied_tools(evts),
    }


def _num_or_null(value: str) -> int | None:
    return int(value) if value.isdigit() else None


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="interns.entrypoint extract-metrics")
    parser.add_argument("--exec-file", required=True)
    parser.add_argument("--job", required=True, choices=JOBS)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--issue", default="")
    parser.add_argument("--pr", default="")
    args = parser.parse_args(argv)

    if not Path(args.exec_file).is_file():
        print(f"extract-metrics: execution file not found: {args.exec_file}", file=sys.stderr)
        return 1

    if not ctx.run_id:
        raise cli.MissingEnvError("GITHUB_RUN_ID unset")

    try:
        record = build_record(
            args.exec_file,
            job=args.job,
            issue=_num_or_null(args.issue),
            pr=_num_or_null(args.pr),
            repo=ctx.repo,
            run_id=int(ctx.run_id),
            run_attempt=ctx.run_attempt,
            interns_ref=args.ref,
        )
    except NoResultEventError as exc:
        print(f"extract-metrics: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(record, separators=(",", ":")))
    return 0
