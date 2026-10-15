import unittest

from interns import execution
from interns.domain import agent_run
from interns.domain.agent_run import AgentRun


def _run(**overrides) -> AgentRun:
    fields = dict(model="m", max_turns=30, mcp_config="/tmp/mcp.json", tools="Read,Grep", allowed_tools="Read,mcp__x__y",
                  disallowed_tools=[], add_dirs=[], debug_file="/tmp/debug.log")
    return AgentRun(**{**fields, **overrides})


def _flag(command: list[str], name: str) -> str:
    return command[command.index(name) + 1]


class BuildCommandTests(unittest.TestCase):
    def test_carries_the_phase_config(self):
        command = agent_run.build_command(_run())
        self.assertEqual(command[:2], ["claude", "-p"])
        self.assertEqual(_flag(command, "--model"), "m")
        self.assertEqual(_flag(command, "--max-turns"), "30")
        self.assertEqual(_flag(command, "--mcp-config"), "/tmp/mcp.json")
        self.assertEqual(_flag(command, "--tools"), "Read,Grep")
        self.assertEqual(_flag(command, "--allowedTools"), "Read,mcp__x__y")
        self.assertEqual(_flag(command, "--debug-file"), "/tmp/debug.log")
        self.assertEqual(_flag(command, "--output-format"), "stream-json")
        self.assertNotIn("--disallowedTools", command)
        self.assertNotIn("--add-dir", command)

    def test_optional_flags_follow_the_config(self):
        command = agent_run.build_command(_run(disallowed_tools=["Write", "Edit"], add_dirs=["/w"]))
        self.assertEqual(_flag(command, "--disallowedTools"), "Write,Edit")
        self.assertEqual(_flag(command, "--add-dir"), "/w")


class BuildEnvTests(unittest.TestCase):
    def test_scrubs_oidc_request_vars_and_sets_both_github_tokens(self):
        base = {"ACTIONS_ID_TOKEN_REQUEST_URL": "u", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "t", "PATH": "/bin", "GH_TOKEN": "old"}
        env = agent_run.build_env(base, "new")
        self.assertEqual(env, {"PATH": "/bin", "GH_TOKEN": "new", "GITHUB_TOKEN": "new"})


def _result(**fields) -> dict:
    return {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3, "total_cost_usd": 0.1, **fields}


class EvaluateTests(unittest.TestCase):
    def test_success(self):
        outcome = agent_run.evaluate([{"type": "system"}, _result()])
        self.assertTrue(outcome.success)
        self.assertEqual(outcome.summary, "turns=3 cost_usd=0.1 denied_tools=none")

    def test_no_result_event_fails(self):
        outcome = agent_run.evaluate([{"type": "system"}])
        self.assertEqual((outcome.success, outcome.summary), (False, "no result event"))

    def test_error_subtype_fails(self):
        self.assertFalse(agent_run.evaluate([_result(subtype="error_max_turns", is_error=True)]).success)

    def test_success_subtype_with_is_error_fails(self):
        self.assertFalse(agent_run.evaluate([_result(is_error=True)]).success)

    def test_turns_above_max_still_succeed_when_the_result_is_success(self):
        self.assertTrue(agent_run.evaluate([_result(num_turns=139)]).success)

    def test_a_denied_tool_call_is_named_in_the_summary_without_its_input(self):
        denial = {"tool_name": "Bash", "tool_input": {"command": "echo secret > f"}}
        outcome = agent_run.evaluate([_result(permission_denials=[denial, denial])])
        self.assertTrue(outcome.success)
        self.assertIn("denied_tools=Bash", outcome.summary)
        self.assertNotIn("secret", outcome.summary)

    def test_a_denied_tool_call_is_listed_by_the_execution_parser(self):
        denial = {"tool_name": "Bash", "tool_input": {"command": "echo hi > f"}, "tool_use_id": "t1"}
        self.assertEqual(execution.permission_denials(_result(permission_denials=[denial])), [denial])
