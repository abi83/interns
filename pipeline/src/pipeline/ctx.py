"""Actions execution context: env vars read once at entrypoint, threaded through to all commands."""

from __future__ import annotations

import os
from dataclasses import dataclass

from . import cli


@dataclass
class ActionsCtx:
    repo: str
    token: str
    server_url: str
    run_id: str
    run_attempt: int
    workspace: str
    event_name: str
    reviewer_bot: str
    step_summary: str

    def run_url(self) -> str:
        return f"{self.server_url}/{self.repo}/actions/runs/{self.run_id}"

    def pr_url(self, number: int) -> str:
        return f"{self.server_url}/{self.repo}/pull/{number}"

    @classmethod
    def from_env(cls) -> ActionsCtx:
        return cls(
            repo=cli.require_env("GITHUB_REPOSITORY"),
            token=cli.require_env("GH_TOKEN"),
            server_url=cli.require_env("GITHUB_SERVER_URL"),
            run_id=os.environ.get("GITHUB_RUN_ID", ""),
            run_attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")),
            workspace=os.environ.get("GITHUB_WORKSPACE", "."),
            event_name=os.environ.get("GITHUB_EVENT_NAME", ""),
            reviewer_bot=os.environ.get("REVIEWER_BOT", ""),
            step_summary=os.environ.get("GITHUB_STEP_SUMMARY", ""),
        )
