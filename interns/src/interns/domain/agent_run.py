"""One headless `claude -p` run: the argv, the environment and the verdict on
its event stream. Pure -- the subprocess lives in interns.steps.run_agent."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

SCRUBBED_ENV_PREFIX = "ACTIONS_ID_TOKEN_REQUEST_"


@dataclass(frozen=True)
class AgentRun:
    model: str
    max_turns: int
    mcp_config: str
    tools: str
    allowed_tools: str
    disallowed_tools: list[str]
    add_dirs: list[str]
    debug_file: str


@dataclass(frozen=True)
class Outcome:
    success: bool
    summary: str


def build_command(run: AgentRun) -> list[str]:
    """`--permission-mode default` is unconditional: a fresh CLI otherwise may
    start in `auto` mode and run tools outside the allowlist without a denial."""
    command = [
        "claude", "-p",
        "--output-format", "stream-json", "--verbose",
        "--permission-mode", "default",
        "--model", run.model,
        "--max-turns", str(run.max_turns),
        "--mcp-config", run.mcp_config,
        "--tools", run.tools,
        "--allowedTools", run.allowed_tools,
        "--debug-file", run.debug_file,
    ]
    if run.disallowed_tools:
        command += ["--disallowedTools", ",".join(run.disallowed_tools)]
    for directory in run.add_dirs:
        command += ["--add-dir", directory]
    return command


def build_env(base: Mapping[str, str], gh_token: str) -> dict[str, str]:
    """The agent must not be able to mint OIDC tokens, and `gh`/`git` inside it
    authenticate with the token handed over explicitly."""
    env = {key: value for key, value in base.items() if not key.startswith(SCRUBBED_ENV_PREFIX)}
    env["GH_TOKEN"] = gh_token
    env["GITHUB_TOKEN"] = gh_token
    return env


def evaluate(events: list[dict], max_turns: int) -> Outcome:
    """Success only on a `result` event with subtype `success` and no error,
    within the turn budget. Reports counts and names only, never agent text."""
    results = [event for event in events if event.get("type") == "result"]
    if not results:
        return Outcome(False, "no result event")
    result = results[-1]
    turns = result.get("num_turns") or 0
    denied = sorted({denial["tool_name"] for denial in result.get("permission_denials") or []})
    facts = f"turns={turns} cost_usd={result.get('total_cost_usd', 'unknown')} denied_tools={','.join(denied) or 'none'}"
    if result.get("subtype") != "success":
        return Outcome(False, f"subtype {result.get('subtype')}; {facts}")
    if result.get("is_error"):
        return Outcome(False, f"is_error; {facts}")
    if turns > max_turns:
        return Outcome(False, f"turns exceed max {max_turns}; {facts}")
    return Outcome(True, facts)
