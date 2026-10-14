"""`run-agent` against a fake `claude` on PATH: the argv and environment it is started with, what
reaches the job log, the execution file it leaves, and that report-run / extract-metrics read it."""

import json
import os
import stat
import sys

import pytest

from testkit.harness import Scenario

FAKE_CLAUDE = """#!{python}
import json, os, sys
record = {{"argv": sys.argv[1:], "stdin": sys.stdin.read(),
          "env": {{k: os.environ.get(k) for k in ("GH_TOKEN", "GITHUB_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_URL",
                                                  "ACTIONS_ID_TOKEN_REQUEST_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN")}}}}
open(os.environ["FAKE_CLAUDE_RECORD"], "w").write(json.dumps(record))
sys.stdout.write(open(os.environ["FAKE_CLAUDE_EVENTS"]).read())
sys.stderr.write("agent stderr chatter\\n")
sys.exit(int(os.environ.get("FAKE_CLAUDE_EXIT", "0")))
"""

PROMPT = "REPO: acme/widgets\nISSUE NUMBER: 7"
DENIAL = {"tool_name": "Bash", "tool_input": {"command": "echo hi > f"}, "tool_use_id": "t1"}
RESULT = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 2, "session_id": "s1",
          "duration_ms": 10, "duration_api_ms": 5, "total_cost_usd": 0.0123, "permission_denials": [DENIAL],
          "modelUsage": {"claude-sonnet-5-5": {"inputTokens": 1, "outputTokens": 2, "costUSD": 0.0123}}}
EVENTS = [
    {"type": "system", "subtype": "init"},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {}}]}},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "echo hi > f"}}]}},
    RESULT,
]


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def run_agent(scenario: Scenario, events: list[dict], *, debug: str = "false", max_turns: int = 30, exit_code: int = 0,
              extra: list[str] | None = None):
    bin_dir = scenario.dir / "claude-bin"
    bin_dir.mkdir(exist_ok=True)
    claude = bin_dir / "claude"
    claude.write_text(FAKE_CLAUDE.format(python=sys.executable))
    claude.chmod(claude.stat().st_mode | stat.S_IEXEC)
    events_file = scenario.dir / "events.jsonl"
    events_file.write_text("".join(json.dumps(e) + "\n" for e in events))
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{scenario.env['PATH']}",
        "FAKE_CLAUDE_RECORD": str(scenario.dir / "record.json"),
        "FAKE_CLAUDE_EVENTS": str(events_file),
        "FAKE_CLAUDE_EXIT": str(exit_code),
        "INTERNS_AGENT_PROMPT": PROMPT,
        "GH_TOKEN": "gh-token",
        "CLAUDE_CODE_OAUTH_TOKEN": "oauth",
        "ACTIONS_ID_TOKEN_REQUEST_URL": "https://oidc.example",
        "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "oidc-secret",
    }
    return scenario.run(
        "interns.entrypoint", "run-agent",
        "--model", "claude-sonnet-5-5", "--max-turns", str(max_turns),
        "--mcp-config", "/tmp/mcp.json", "--tools", "Read,Grep", "--allowed-tools", "Read,mcp__gh-issues__comment_issue",
        "--execution-file", str(scenario.dir / "execution.jsonl"), "--debug-file", str(scenario.dir / "debug.log"),
        "--debug", debug, *(extra or []), env=env,
    )


def recorded(scenario: Scenario) -> dict:
    return json.loads((scenario.dir / "record.json").read_text())


def test_launches_claude_with_the_phase_config_and_a_scrubbed_env(scenario):
    result = run_agent(scenario, EVENTS, extra=["--disallowed-tools", "WebFetch,Write", "--add-dir", "/wiki"])

    assert result.returncode == 0
    call = recorded(scenario)
    argv = call["argv"]
    assert argv[argv.index("--permission-mode") + 1] == "default"
    assert argv[argv.index("--model") + 1] == "claude-sonnet-5-5"
    assert argv[argv.index("--max-turns") + 1] == "30"
    assert argv[argv.index("--mcp-config") + 1] == "/tmp/mcp.json"
    assert argv[argv.index("--tools") + 1] == "Read,Grep"
    assert argv[argv.index("--allowedTools") + 1] == "Read,mcp__gh-issues__comment_issue"
    assert argv[argv.index("--disallowedTools") + 1] == "WebFetch,Write"
    assert argv[argv.index("--add-dir") + 1] == "/wiki"
    assert argv[argv.index("--debug-file") + 1] == str(scenario.dir / "debug.log")
    assert call["stdin"] == PROMPT
    assert call["env"] == {"GH_TOKEN": "gh-token", "GITHUB_TOKEN": "gh-token", "CLAUDE_CODE_OAUTH_TOKEN": "oauth",
                           "ACTIONS_ID_TOKEN_REQUEST_URL": None, "ACTIONS_ID_TOKEN_REQUEST_TOKEN": None}


def test_publishes_the_execution_and_debug_files(scenario):
    result = run_agent(scenario, EVENTS)

    assert result.outputs == {"execution_file": str(scenario.dir / "execution.jsonl"),
                              "debug_file": str(scenario.dir / "debug.log")}
    lines = (scenario.dir / "execution.jsonl").read_text().splitlines()
    assert [json.loads(line)["type"] for line in lines] == ["system", "assistant", "assistant", "result"]


def test_prints_no_agent_output_when_debug_is_off(scenario):
    result = run_agent(scenario, EVENTS)

    assert "echo hi" not in result.stdout + result.stderr
    assert "chatter" not in result.stdout + result.stderr
    assert "run-agent: success: turns=2 cost_usd=0.0123 denied_tools=Bash" in result.stderr


def test_prints_the_agent_stream_when_debug_is_on(scenario):
    result = run_agent(scenario, EVENTS, debug="true")

    assert "echo hi" in result.stdout
    assert "chatter" in result.stderr


def test_a_denied_tool_call_is_in_the_result_and_the_run_still_succeeds(scenario):
    run_agent(scenario, EVENTS)

    result = scenario.run("interns.entrypoint", "extract-metrics", "--exec-file", str(scenario.dir / "execution.jsonl"),
                          "--job", "estimator", "--ref", "refs/tags/v0", "--issue", "7")

    record = json.loads(result.stdout)
    assert record["permission_denials"] == 1
    assert record["denied_tools"] == ["Bash"]


def test_extract_metrics_reads_the_launcher_stream(scenario):
    run_agent(scenario, EVENTS)

    result = scenario.run("interns.entrypoint", "extract-metrics", "--exec-file", str(scenario.dir / "execution.jsonl"),
                          "--job", "estimator", "--ref", "refs/tags/v0", "--issue", "7")

    record = json.loads(result.stdout)
    assert record["agent_result"] == "success"
    assert record["session_id"] == "s1"
    assert record["tool_calls"] == {"Read": 1, "Bash:other": 1}
    assert record["models"]["claude-sonnet-5-5"]["cost_usd"] == 0.0123


def test_report_run_reads_the_launcher_stream(scenario):
    run_agent(scenario, EVENTS)

    scenario.run("interns.entrypoint", "report-run", "--phase", "Estimation",
                 "--exec-file", str(scenario.dir / "execution.jsonl"), "--issue", "7")

    [(number, body)] = scenario.comments("issue")
    assert number == "7"
    assert "cost: $0.0123" in body


@pytest.mark.parametrize("events", [
    [{"type": "system"}],
    [{**RESULT, "subtype": "error_max_turns", "is_error": True}],
    [{**RESULT, "is_error": True}],
    [{**RESULT, "num_turns": 31}],
], ids=["no-result", "error-subtype", "is-error", "turns-over-max"])
def test_fails_unless_the_result_event_is_a_clean_success(scenario, events):
    result = run_agent(scenario, events)

    assert result.returncode == 1
    assert "run-agent: failed" in result.stderr
    assert result.outputs["execution_file"] == str(scenario.dir / "execution.jsonl")


def test_missing_github_token_fails_fast(scenario):
    result = scenario.run("interns.entrypoint", "run-agent", "--model", "m", "--max-turns", "1", "--mcp-config", "c",
                          "--tools", "Read", "--allowed-tools", "Read", "--execution-file", "e", "--debug-file", "d",
                          "--debug", "false", env={"GH_TOKEN": "", "INTERNS_AGENT_PROMPT": PROMPT})

    assert result.returncode == 1
    assert "GH_TOKEN unset" in result.stderr
