"""`config` command: resolves one agent's settings (or the checks-ignore
list) from interns.yml and prints them for `$GITHUB_OUTPUT` capture."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from .. import cli, config
from ..config import AgentConfig, ConfigError


def _suffix(tools: list[str]) -> str:
    return "".join(f",{tool}" for tool in tools)


def _flag(name: str, tools: list[str]) -> str:
    return f'{name} "{",".join(tools)}"' if tools else ""


def _bool(value: bool) -> str:
    return "true" if value else "false"


@dataclass(frozen=True)
class _Field:
    """One resolved agent setting: its `key=value` stdout line and, when it
    appears in the stderr summary, that summary's own key and value."""

    key: str
    value: str
    summary: tuple[str, str] | None


def _plain(key: str, value: str) -> _Field:
    return _Field(key, value, (key, value))


def _agent_fields(cfg: AgentConfig, wiki_path: str) -> list[_Field]:
    return [
        _plain("model", cfg.model),
        _plain("max_turns", str(cfg.max_turns)),
        _plain("timeout_minutes", str(cfg.timeout_minutes)),
        _plain("max_output_tokens", str(cfg.max_output_tokens)),
        _plain("cost_warn_usd", str(cfg.cost_warn_usd)),
        _Field("tools_suffix", _suffix(config.builtin_tool_names(cfg.allowed_tools)), None),
        _Field("allowed_tools_suffix", _suffix(cfg.allowed_tools), ("allowed_tools", ",".join(cfg.allowed_tools))),
        _Field(
            "disallowed_tools_arg",
            _flag("--disallowedTools", cfg.disallowed_tools),
            ("disallowed_tools", ",".join(cfg.disallowed_tools)),
        ),
        _plain("wiki_enabled", _bool(cfg.wiki_enabled)),
        _Field("wiki_repo", cfg.wiki_repo, None),
        _Field("wiki_dir", wiki_path, None),
        _Field("add_dir_arg", f"--add-dir {wiki_path}" if wiki_path else "", None),
        _plain("debug", _bool(cfg.debug)),
    ]


def _print_agent_config(cfg: AgentConfig, agent: str) -> None:
    wiki_path = config.wiki_dir(cfg.wiki_repo, cli.require_env("GITHUB_WORKSPACE")) if cfg.wiki_enabled else ""
    fields = _agent_fields(cfg, wiki_path)
    for field in fields:
        print(f"{field.key}={field.value}")
    summary = " ".join(f"{key}={value}" for key, value in (f.summary for f in fields if f.summary))
    print(f"agent-config[{agent}]: {summary}", file=sys.stderr)


def main(argv: list[str]) -> int:
    parser = cli.build_parser("config")
    parser.add_argument("--config", default=config.config_path())
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("agent-config")
    p.add_argument("agent")

    sub.add_parser("checks-ignore")

    args = parser.parse_args(argv)

    try:
        data = config.load_raw(args.config)
        if args.command == "agent-config":
            _print_agent_config(config.resolve_agent_config(data, args.agent, args.config), args.agent)
        elif args.command == "checks-ignore":
            print(json.dumps(config.checks_config(data, args.config).ignore))
    except ConfigError as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 1
    return 0
