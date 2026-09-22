"""Appends pipeline-metrics records (from extract_metrics) to metrics.jsonl
on the orphan `metrics` branch, one commit per call. Callers serialise
appends with a concurrency group; on a losing push race this retries by
re-fetching the branch tip and re-appending. The branch is created on first
use.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .ctx import ActionsCtx

BRANCH = "metrics"
FILE = "metrics.jsonl"
RETRIES = 3
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


class AppendMetricsError(RuntimeError):
    """Raised when a record file fails validation, or every push attempt is
    exhausted."""


def _read_records(files: list[str]) -> str:
    """One compact JSON line per file, concatenated -- validates every
    record is a JSON object before touching the remote."""
    lines = []
    for name in files:
        path = Path(name)
        if not path.is_file():
            raise AppendMetricsError(f"no such file: {name}")
        try:
            record = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise AppendMetricsError(f"not a JSON object: {name}") from exc
        if not isinstance(record, dict):
            raise AppendMetricsError(f"not a JSON object: {name}")
        lines.append(json.dumps(record, separators=(",", ":")))
    return "".join(line + "\n" for line in lines)


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _push_attempt(work: Path, records: str, remote: str, run_id: str) -> bool:
    """One fetch/checkout/append/commit/push cycle against `remote`. False
    on any failing step -- including a losing push race -- so the caller can
    retry from a clean fetch."""
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    setup = [
        ["init", "-q"],
        ["config", "user.name", BOT_NAME],
        ["config", "user.email", BOT_EMAIL],
        ["config", "commit.gpgsign", "false"],
        ["remote", "add", "origin", remote],
    ]
    for args in setup:
        if _run_git(args, work).returncode != 0:
            return False

    fetched = _run_git(["fetch", "-q", "--depth=1", "origin", BRANCH], work).returncode == 0
    checkout = ["checkout", "-q", "-b", BRANCH, "FETCH_HEAD"] if fetched \
        else ["checkout", "-q", "--orphan", BRANCH]
    if _run_git(checkout, work).returncode != 0:
        return False
    if not fetched:
        (work / FILE).write_text("")

    with open(work / FILE, "a") as f:
        f.write(records)

    if _run_git(["add", FILE], work).returncode != 0:
        return False
    message = f"chore(metrics): append records from run {run_id}"
    if _run_git(["commit", "-q", "-m", message], work).returncode != 0:
        return False
    return _run_git(["push", "-q", "origin", f"HEAD:{BRANCH}"], work).returncode == 0


def append_records(files: list[str], *, remote: str, run_id: str,
                    retries: int = RETRIES, sleep=time.sleep) -> int:
    """Validates `files` and appends them to the `metrics` branch on
    `remote`, retrying (with backoff) on a losing push race. Returns the
    number of records appended, or 0 (doing nothing) when `files` yields no
    records."""
    records = _read_records(files)
    if not records:
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "work"
        for attempt in range(1, retries + 1):
            if _push_attempt(work, records, remote, run_id):
                return records.count("\n")
            print(f"append-metrics: attempt {attempt}/{retries} failed", file=sys.stderr)
            if attempt < retries:
                sleep(attempt * 3)

    raise AppendMetricsError(f"push to {BRANCH} failed after {retries} attempts")


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="pipeline.entrypoint append-metrics")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args(argv)

    server = ctx.server_url or "https://github.com"
    run_id = ctx.run_id or "unknown"
    remote = f"https://x-access-token:{ctx.token}@{server.removeprefix('https://')}/{ctx.repo}.git"

    try:
        count = append_records(args.files, remote=remote, run_id=run_id)
    except AppendMetricsError as exc:
        print(f"append-metrics: {exc}", file=sys.stderr)
        return 1

    print(f"append-metrics: appended {count} record(s) to {BRANCH}")
    return 0
