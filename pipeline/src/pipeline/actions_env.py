"""Links built from the Actions env the workflow already exports."""

from __future__ import annotations

from . import cli


def run_url(repo: str) -> str:
    """Link to the current workflow run, for "see the run" lines in
    comments. Reads the Actions env the workflow already exports."""
    server = cli.require_env("GITHUB_SERVER_URL")
    run_id = cli.require_env("GITHUB_RUN_ID")
    return f"{server}/{repo}/actions/runs/{run_id}"


def pr_url(repo: str, number: int, *, server_url: str | None = None) -> str:
    """Link to PR `number`. Reads GITHUB_SERVER_URL from the Actions env by
    default; pass `server_url` explicitly for a caller (pipeline.run_summary)
    that already threads it as a parameter rather than reading os.environ
    itself, so it stays independently testable."""
    server = server_url or cli.require_env("GITHUB_SERVER_URL")
    return f"{server}/{repo}/pull/{number}"
