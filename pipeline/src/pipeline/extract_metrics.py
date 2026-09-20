"""Parses one claude-code-action execution file into a single
pipeline-metrics record (one JSON object), for append_metrics to persist.

Bump SCHEMA_VERSION and .github/pipeline-metrics.schema.json together on any
breaking shape change.

extract-metrics.sh is a thin shim over this module.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
JOBS = ("refiner", "estimator", "coder", "reviewer")


class NoResultEventError(RuntimeError):
    """The execution file has no `result` event -- a killed run can leave a
    truncated file."""


def _tool_calls(events: list[dict]) -> dict[str, int]:
    """Main-agent tool_use blocks only, grouped by name -- a sub-agent
    (isSidechain) invocation isn't a top-level pipeline action."""
    counts: dict[str, int] = {}
    for event in events:
        if event.get("type") != "assistant" or event.get("isSidechain"):
            continue
        for block in event.get("message", {}).get("content") or []:
            if block.get("type") == "tool_use":
                name = block["name"]
                counts[name] = counts.get(name, 0) + 1
    return counts


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
                  repo: str, run_id: int, run_attempt: int) -> dict:
    events = json.loads(Path(exec_file).read_text())
    results = [e for e in events if e.get("type") == "result"]
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
        "session_id": result.get("session_id"),
        "agent_result": result.get("subtype"),
        "num_turns": result.get("num_turns"),
        "duration_ms": result.get("duration_ms"),
        "duration_api_ms": result.get("duration_api_ms"),
        "models": _models(result.get("modelUsage") or {}),
        "tool_calls": _tool_calls(events),
    }


def _num_or_null(value: str) -> int | None:
    return int(value) if value.isdigit() else None


def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="python -m pipeline.extract_metrics")
    parser.add_argument("exec_file")
    parser.add_argument("--job", required=True, choices=JOBS)
    parser.add_argument("--issue", default="")
    parser.add_argument("--pr", default="")
    args = parser.parse_args(argv)

    if not Path(args.exec_file).is_file():
        print(f"extract-metrics: execution file not found: {args.exec_file}", file=sys.stderr)
        return 1

    try:
        record = build_record(
            args.exec_file,
            job=args.job,
            issue=_num_or_null(args.issue),
            pr=_num_or_null(args.pr),
            repo=os.environ["GITHUB_REPOSITORY"],
            run_id=int(os.environ["GITHUB_RUN_ID"]),
            run_attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")),
        )
    except NoResultEventError as exc:
        print(f"extract-metrics: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(record, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
