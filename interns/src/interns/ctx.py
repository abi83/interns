"""Actions execution context: the always-present env vars read once at the
entrypoint; the rest are required accessors that fail only in the command
that needs them."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import cli, config
from .domain import actor_guard, routing


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

    def route_config(self, handles: str) -> routing.RouteConfig:
        config_path = self.config_path
        trigger = config.reviewer_trigger_config(config.load_raw(config_path), config_path)
        return routing.RouteConfig.parse(handles, trigger)

    def _payload(self) -> dict:
        return json.loads(Path(cli.require_env("GITHUB_EVENT_PATH")).read_text())

    def event(self) -> routing.GithubEvent:
        return routing.parse_event(cli.require_env("GITHUB_EVENT_NAME"), self._payload())

    def actors(self) -> tuple[actor_guard.Actor, ...]:
        return actor_guard.event_actors(cli.require_env("GITHUB_EVENT_NAME"), self._payload())

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
