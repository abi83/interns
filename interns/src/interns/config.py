"""interns.yml loader and validator -- the only reader of the pipeline config
file (schema: .github/interns.schema.json).

Both the agent-config resolution (interns.steps.show_config) and the
reviewer's checks-ignore list (interns.steps.wait_for_checks) go
through `load_raw` here, so a malformed file fails the same way no matter
which setting the caller needed.
"""

from __future__ import annotations

import functools
import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SCHEMA_PATH = Path(__file__).resolve().parents[3] / ".github" / "interns.schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text())

# The pipeline's own built-in fallback layer, loaded through the identical
# schema-validated path as a consumer's file. The installer renders
# a fresh consumer's starter .github/interns.yml from this file (all keys
# commented out).
_DEFAULTS_CONFIG_PATH = Path(__file__).resolve().parents[3] / "templates" / "config" / "defaults.yml"


class ConfigError(RuntimeError):
    """interns.yml is missing yq, malformed, or fails schema/range validation."""


@dataclass
class AgentConfig:
    model: str
    max_turns: int
    timeout_minutes: int
    max_output_tokens: int
    cost_warn_usd: float
    allowed_tools: list[str]
    disallowed_tools: list[str]
    wiki_enabled: bool
    wiki_repo: str
    debug: bool


@dataclass
class ChecksConfig:
    ignore: list[str]
    timeout_seconds: float
    poll_seconds: float
    settle_seconds: float


@dataclass
class ReviewLoopConfig:
    max_fix_rounds: int
    max_automatic_reviews: int


def _yaml_to_json(path: str) -> object:
    try:
        proc = subprocess.run(["yq", "-o=json", "-I=0", ".", path], capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise ConfigError("the `yq` CLI is not installed or not on PATH") from exc
    if proc.returncode != 0:
        raise ConfigError(f"{path} is not valid YAML: {(proc.stderr or '').strip()}")
    return json.loads(proc.stdout)


def load_raw(path: str) -> dict:
    """The parsed, schema-validated config file, or {} when it doesn't exist
    or holds only comments (a freshly installed one)."""
    if not os.path.isfile(path):
        return {}
    data = _yaml_to_json(path)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} is not valid YAML or not a mapping")
    _validate_schema(data, path)
    return data


def _schema_properties(node: dict) -> dict:
    ref = node.get("$ref")
    if ref:
        node = _SCHEMA["definitions"][ref.rsplit("/", 1)[-1]]
    return node.get("properties", {})


KNOWN_AGENTS = tuple(_schema_properties(_SCHEMA)["agents"]["properties"])
KNOWN_SIZES = tuple(_schema_properties(_SCHEMA)["auto_proceed"]["properties"])


def _unknown_key_error(parents: tuple[str, ...], key: str, path: str) -> ConfigError:
    if not parents:
        return ConfigError(f"unknown top-level key '{key}' in {path}")
    if parents == ("agents",):
        return ConfigError(f"unknown agent '{key}' in {path}")
    return ConfigError(f"unknown key '{'.'.join((*parents, key))}' in {path}")


def _validate_schema(data: dict, path: str, node: dict = _SCHEMA, parents: tuple[str, ...] = ()) -> None:
    """Rejects keys the schema doesn't declare, at every nesting level."""
    known = _schema_properties(node)
    for key, value in data.items():
        if key not in known:
            raise _unknown_key_error(parents, key, path)
        if isinstance(value, dict):
            _validate_schema(value, path, known[key], (*parents, key))


def _is_int_ge(value: object, floor: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= floor


def _is_num_gt0(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


@dataclass(frozen=True)
class _Rule:
    valid: Callable[[object], bool]
    expected: str
    cast: Callable[[Any], Any]
    note: str = ""


_POSITIVE_INT = _Rule(lambda v: _is_int_ge(v, 1), "a positive integer", int)
_POSITIVE_NUMBER = _Rule(_is_num_gt0, "a positive number", float)

_AGENT_RULES = {
    "max_turns": _POSITIVE_INT,
    "timeout_minutes": _POSITIVE_INT,
    "max_output_tokens": _Rule(
        lambda v: _is_int_ge(v, 16000), "an integer >= 16000", int, " -- it is a safety ceiling, not a cost lever"
    ),
    "cost_warn_usd": _POSITIVE_NUMBER,
}
_CHECKS_RULES = {
    "timeout_seconds": _POSITIVE_NUMBER,
    "poll_seconds": _POSITIVE_NUMBER,
    "settle_seconds": _POSITIVE_NUMBER,
}
_REVIEW_LOOP_RULES = {
    "max_fix_rounds": _POSITIVE_INT,
    "max_automatic_reviews": _POSITIVE_INT,
}


def _validated(rule: _Rule, value: object, label: str, suffix: str = ""):
    if not rule.valid(value):
        raise ConfigError(f"{label} must be {rule.expected} (got '{value}'){suffix}{rule.note}")
    return rule.cast(value)


@functools.lru_cache(maxsize=1)
def _builtin_data() -> dict:
    """The shipped defaults, loaded and schema-validated exactly like a
    consumer's own config file."""
    return load_raw(str(_DEFAULTS_CONFIG_PATH))


def _tool_list(block: dict, key: str, where: str) -> list[str]:
    value = block.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(f"{where}.{key} must be a YAML list of tool names")
    for tool in value:
        if not isinstance(tool, str) or not tool:
            raise ConfigError(f"{where}.{key} entries must be non-empty strings (got {tool!r})")
        if any(ch in tool for ch in '\n,"'):
            raise ConfigError(f"{where}.{key} entry {tool!r} must not contain a newline, comma or double quote")
    return value


def _union(*lists: list[str]) -> list[str]:
    return list(dict.fromkeys(item for items in lists for item in items))


def _resolve_tool_lists(defaults_block: dict, agent_block: dict, agent: str) -> tuple[list[str], list[str]]:
    """Consumer-only lists: `defaults` and the agent's own block add up. Deny
    beats allow, so an exactly-matching denied entry is dropped from allow;
    the same entry in both lists of one scope is a contradiction."""
    allowed: list[list[str]] = []
    disallowed: list[list[str]] = []
    for block, where in ((defaults_block, "defaults"), (agent_block, f"agents.{agent}")):
        scope_allowed = _tool_list(block, "allowed_tools", where)
        scope_disallowed = _tool_list(block, "disallowed_tools", where)
        contradiction = set(scope_allowed) & set(scope_disallowed)
        if contradiction:
            raise ConfigError(f"{where} both allows and disallows {sorted(contradiction)}")
        allowed.append(scope_allowed)
        disallowed.append(scope_disallowed)
    denied = _union(*disallowed)
    return [tool for tool in _union(*allowed) if tool not in denied], denied


def builtin_tool_names(tools: list[str]) -> list[str]:
    """`--tools` takes bare built-in names; `Bash(npm run *)` contributes `Bash`, MCP tools contribute nothing."""
    return _union([tool.split("(", 1)[0] for tool in tools if not tool.startswith("mcp__")])


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
    if not model:
        raise ConfigError("model resolved empty")
    limits: dict[str, Any] = {key: _validated(rule, resolve(key), key) for key, rule in _AGENT_RULES.items()}

    allowed_tools, disallowed_tools = _resolve_tool_lists(defaults_block, agent_block, agent)

    wiki = data.get("wiki") or {}
    wiki_enabled = bool(wiki.get("enabled", False))
    wiki_repo = str(wiki.get("url") or "")
    if wiki_enabled and not wiki_repo:
        raise ConfigError(f"wiki.enabled is true but wiki.url is unset in {path}")

    debug = bool(data.get("debug", False))

    return AgentConfig(
        model=str(model),
        **limits,
        allowed_tools=allowed_tools,
        disallowed_tools=disallowed_tools,
        wiki_enabled=wiki_enabled,
        wiki_repo=wiki_repo,
        debug=debug,
    )


def _section_value(consumer: dict, builtin: dict, section: str, key: str):
    """Consumer file, then the shipped defaults; absent from both is a bug in the defaults."""
    for block in (consumer, builtin):
        if key in block:
            return block[key]
    raise ConfigError(f"{section}.{key} is set neither in the config nor in the shipped defaults")


def _section_limits(data: dict, section: str, rules: dict[str, _Rule], path: str) -> dict:
    consumer = data.get(section) or {}
    builtin = _builtin_data().get(section) or {}
    return {
        key: _validated(rule, _section_value(consumer, builtin, section, key), f"{section}.{key}", f" in {path}")
        for key, rule in rules.items()
    }


def checks_config(data: dict, path: str) -> ChecksConfig:
    ignore = (data.get("checks") or {}).get("ignore", [])
    if not isinstance(ignore, list):
        raise ConfigError(f"checks.ignore must be a YAML list of check names in {path}")
    return ChecksConfig(ignore=[str(name) for name in ignore], **_section_limits(data, "checks", _CHECKS_RULES, path))


def review_loop_config(data: dict, path: str) -> ReviewLoopConfig:
    return ReviewLoopConfig(**_section_limits(data, "review_loop", _REVIEW_LOOP_RULES, path))


def auto_proceed_config(data: dict, path: str) -> dict[str, bool]:
    """Per size label: does an estimated issue go straight to the coder?
    Merged key by key, so a consumer overriding one size keeps the rest."""
    consumer = data.get("auto_proceed") or {}
    builtin = _builtin_data().get("auto_proceed") or {}
    resolved: dict[str, bool] = {}
    for size in KNOWN_SIZES:
        value = consumer.get(size, builtin.get(size))
        if not isinstance(value, bool):
            raise ConfigError(f"auto_proceed.{size} must be true or false (got '{value}') in {path}")
        resolved[size] = value
    return resolved


def wiki_dir(wiki_repo: str, workspace: str) -> str:
    """Next to the repo checkout, where agents look for it."""
    return str(Path(workspace).parent / wiki_repo.rsplit("/", 1)[-1])


def config_path() -> str:
    return os.environ.get("INTERNS_CONFIG", ".github/interns.yml")
