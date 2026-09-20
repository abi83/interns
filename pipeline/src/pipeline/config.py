"""interns.yml loader and validator -- the only reader of the pipeline config
file (schema: .github/interns.schema.json).

Both the agent-config resolution (agent-config.sh) and the reviewer's
checks-ignore list (wait-for-checks.sh) go through `load_raw` here, so a
malformed file fails the same way no matter which setting the caller needed.
"""

from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

KNOWN_TOP_KEYS = ("defaults", "agents", "wiki", "checks")
KNOWN_AGENTS = ("refiner", "estimator", "coder", "reviewer")
KNOWN_LIMIT_KEYS = ("model", "max_turns", "timeout_minutes", "max_output_tokens", "cost_warn_usd", "disallowed_tools")
KNOWN_WIKI_KEYS = ("enabled", "url")

# The pipeline's own built-in fallback layer: the same file
# installer/src/interns_install/install_files.py seeds a fresh consumer's
# .github/interns.yml from, loaded through the identical schema-validated
# path as a consumer's file. One file, two consumers -- nothing here to
# drift from the values a fresh install actually ships.
_TEMPLATE_CONFIG_PATH = Path(__file__).resolve().parents[3] / "templates" / "config" / "interns.yml"


class ConfigError(RuntimeError):
    """interns.yml is missing yq, malformed, or fails schema/range validation."""


@dataclass
class AgentConfig:
    model: str
    max_turns: int
    timeout_minutes: int
    max_output_tokens: int
    cost_warn_usd: float
    disallowed_tools: list[str]
    wiki_enabled: bool
    wiki_repo: str


def _yaml_to_json(path: str) -> object:
    try:
        proc = subprocess.run(["yq", "-o=json", "-I=0", ".", path], capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise ConfigError("the `yq` CLI is not installed or not on PATH") from exc
    if proc.returncode != 0:
        raise ConfigError(f"{path} is not valid YAML: {(proc.stderr or '').strip()}")
    return json.loads(proc.stdout)


def load_raw(path: str) -> dict:
    """The parsed, schema-validated config file, or {} when it doesn't exist."""
    if not os.path.isfile(path):
        return {}
    data = _yaml_to_json(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} is not valid YAML or not a mapping")
    _validate_schema(data, path)
    return data


def _validate_schema(data: dict, path: str) -> None:
    for key in data:
        if key not in KNOWN_TOP_KEYS:
            raise ConfigError(f"unknown top-level key '{key}' in {path}")

    for key in data.get("defaults") or {}:
        if key not in KNOWN_LIMIT_KEYS:
            raise ConfigError(f"unknown key 'defaults.{key}' in {path}")

    for agent, block in (data.get("agents") or {}).items():
        if agent not in KNOWN_AGENTS:
            raise ConfigError(f"unknown agent '{agent}' in {path}")
        for key in block or {}:
            if key not in KNOWN_LIMIT_KEYS:
                raise ConfigError(f"unknown key 'agents.{agent}.{key}' in {path}")

    for key in data.get("wiki") or {}:
        if key not in KNOWN_WIKI_KEYS:
            raise ConfigError(f"unknown key 'wiki.{key}' in {path}")


def _is_int_ge(value: object, floor: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= floor


def _is_num_gt0(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


@functools.lru_cache(maxsize=1)
def _builtin_data() -> dict:
    """The shipped template, loaded and schema-validated exactly like a
    consumer's own config file."""
    return load_raw(str(_TEMPLATE_CONFIG_PATH))


def resolve_agent_config(data: dict, agent: str, path: str) -> AgentConfig:
    """Precedence per key: agents.<name>.<key> > defaults.<key> from the
    consumer's file, then the same two layers from the shipped template.
    There is no other override layer."""
    if agent not in KNOWN_AGENTS:
        raise ConfigError(f"unknown agent '{agent}'")

    agent_block = (data.get("agents") or {}).get(agent) or {}
    defaults_block = data.get("defaults") or {}
    builtin = _builtin_data()
    builtin_agent_block = (builtin.get("agents") or {}).get(agent) or {}
    builtin_defaults_block = builtin.get("defaults") or {}

    def resolve(key: str):
        for block in (agent_block, defaults_block, builtin_agent_block, builtin_defaults_block):
            if key in block:
                return block[key]
        return None

    model = resolve("model")
    max_turns = resolve("max_turns")
    timeout_minutes = resolve("timeout_minutes")
    max_output_tokens = resolve("max_output_tokens")
    cost_warn_usd = resolve("cost_warn_usd")

    disallowed_tools = resolve("disallowed_tools")
    if disallowed_tools is not None and not isinstance(disallowed_tools, list):
        raise ConfigError(
            f"agents.{agent}.disallowed_tools / defaults.disallowed_tools must be a YAML list of tool names"
        )
    disallowed_tools = disallowed_tools or []

    if not model:
        raise ConfigError("model resolved empty")
    if not _is_int_ge(max_turns, 1):
        raise ConfigError(f"max_turns must be a positive integer (got '{max_turns}')")
    if not _is_int_ge(timeout_minutes, 1):
        raise ConfigError(f"timeout_minutes must be a positive integer (got '{timeout_minutes}')")
    if not _is_int_ge(max_output_tokens, 16000):
        raise ConfigError(
            f"max_output_tokens must be an integer >= 16000 (got '{max_output_tokens}') "
            "-- it is a safety ceiling, not a cost lever"
        )
    if not _is_num_gt0(cost_warn_usd):
        raise ConfigError(f"cost_warn_usd must be a positive number (got '{cost_warn_usd}')")
    if any("\n" in tool for tool in disallowed_tools):
        raise ConfigError("disallowed_tools must not contain newlines")

    wiki = data.get("wiki") or {}
    wiki_enabled = bool(wiki.get("enabled", False))
    wiki_repo = str(wiki.get("url") or "")
    if wiki_enabled and not wiki_repo:
        raise ConfigError(f"wiki.enabled is true but wiki.url is unset in {path}")

    return AgentConfig(
        model=str(model),
        max_turns=int(max_turns),
        timeout_minutes=int(timeout_minutes),
        max_output_tokens=int(max_output_tokens),
        cost_warn_usd=float(cost_warn_usd),
        disallowed_tools=[str(tool) for tool in disallowed_tools],
        wiki_enabled=wiki_enabled,
        wiki_repo=wiki_repo,
    )


def checks_ignore(data: dict, path: str) -> list[str]:
    """The reviewer gate's non-blocking advisory check names
    (`checks.ignore`). A malformed value fails loudly, same as every other
    key in this file -- no silent fallback to an empty list."""
    ignore = (data.get("checks") or {}).get("ignore", [])
    if not isinstance(ignore, list):
        raise ConfigError(f"checks.ignore must be a YAML list of check names in {path}")
    return [str(name) for name in ignore]


def _main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pipeline.config")
    parser.add_argument("--config", default=os.environ.get("INTERNS_CONFIG", ".github/interns.yml"))
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("agent-config")
    p.add_argument("agent")

    sub.add_parser("checks-ignore")

    args = parser.parse_args(argv)

    try:
        data = load_raw(args.config)
        if args.command == "agent-config":
            cfg = resolve_agent_config(data, args.agent, args.config)
            for line in (
                f"model={cfg.model}",
                f"max_turns={cfg.max_turns}",
                f"timeout_minutes={cfg.timeout_minutes}",
                f"max_output_tokens={cfg.max_output_tokens}",
                f"cost_warn_usd={cfg.cost_warn_usd}",
                f"disallowed_tools={','.join(cfg.disallowed_tools)}",
                f"wiki_enabled={'true' if cfg.wiki_enabled else 'false'}",
                f"wiki_repo={cfg.wiki_repo}",
            ):
                print(line)
            print(
                f"agent-config[{args.agent}]: model={cfg.model} max_turns={cfg.max_turns} "
                f"timeout_minutes={cfg.timeout_minutes} max_output_tokens={cfg.max_output_tokens} "
                f"cost_warn_usd={cfg.cost_warn_usd} disallowed_tools={','.join(cfg.disallowed_tools)} "
                f"wiki_enabled={'true' if cfg.wiki_enabled else 'false'}",
                file=sys.stderr,
            )
        elif args.command == "checks-ignore":
            print(json.dumps(checks_ignore(data, args.config)))
    except ConfigError as exc:
        print(f"config: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
