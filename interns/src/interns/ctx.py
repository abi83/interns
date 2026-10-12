"""Actions execution context: the always-present env vars read once at the
entrypoint; the rest are required accessors that fail only in the command
that needs them."""

from __future__ import annotations

import os
from dataclasses import dataclass

from . import cli, config


@dataclass
class ActionsCtx:
    repo: str
    token: str
    server_url: str

    @property
    def run_id(self) -> str:
        return cli.require_env("GITHUB_RUN_ID")

    @property
    def run_attempt(self) -> int:
        return int(cli.require_env("GITHUB_RUN_ATTEMPT"))

    @property
    def workspace(self) -> str:
        return cli.require_env("GITHUB_WORKSPACE")

    @property
    def reviewer_bot(self) -> str:
        return cli.require_env("REVIEWER_BOT")

    @property
    def step_summary(self) -> str:
        return cli.require_env("GITHUB_STEP_SUMMARY")

    @property
    def event_name(self) -> str:
        return os.environ.get("GITHUB_EVENT_NAME", "")

    @property
    def config_path(self) -> str:
        return config.config_path()

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
        )
