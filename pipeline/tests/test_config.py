import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pipeline import config


def _cp(stdout: str = "", returncode: int = 0, stderr: str = ""):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def _yaml(data: object, *, exists: bool = True):
    """Patch _yaml_to_json and os.path.isfile so load_raw(path) returns `data`."""
    return (
        patch("pipeline.config.os.path.isfile", return_value=exists),
        patch("pipeline.config._yaml_to_json", return_value=data),
    )


def _load(data: object) -> dict:
    isfile_p, yaml_p = _yaml(data)
    with isfile_p, yaml_p:
        return config.load_raw("interns.yml")


class LoadRawTests(unittest.TestCase):
    def test_missing_file_is_an_empty_config(self):
        isfile_p, _ = _yaml({}, exists=False)
        with isfile_p:
            self.assertEqual(config.load_raw("none.yml"), {})

    def test_non_mapping_top_level_is_rejected(self):
        with self.assertRaisesRegex(config.ConfigError, "not valid YAML or not a mapping"):
            _load([1, 2])

    def test_yq_failure_is_surfaced(self):
        isfile_p = patch("pipeline.config.os.path.isfile", return_value=True)
        run_p = patch("pipeline.config.subprocess.run", return_value=_cp(returncode=1, stderr="bad yaml"))
        with isfile_p, run_p:
            with self.assertRaisesRegex(config.ConfigError, "not valid YAML"):
                config.load_raw("interns.yml")

    def test_missing_yq_binary_is_surfaced(self):
        isfile_p = patch("pipeline.config.os.path.isfile", return_value=True)
        run_p = patch("pipeline.config.subprocess.run", side_effect=FileNotFoundError())
        with isfile_p, run_p:
            with self.assertRaisesRegex(config.ConfigError, "yq"):
                config.load_raw("interns.yml")

    def test_unknown_top_level_key(self):
        with self.assertRaisesRegex(config.ConfigError, "unknown top-level key 'junk'"):
            _load({"junk": 1})

    def test_unknown_defaults_key(self):
        with self.assertRaisesRegex(config.ConfigError, "unknown key 'defaults.max_tokens'"):
            _load({"defaults": {"max_tokens": 100}})

    def test_unknown_agent_block(self):
        with self.assertRaisesRegex(config.ConfigError, "unknown agent 'tester'"):
            _load({"agents": {"tester": {"max_turns": 5}}})

    def test_unknown_agent_key(self):
        with self.assertRaisesRegex(config.ConfigError, "unknown key 'agents.coder.bogus'"):
            _load({"agents": {"coder": {"bogus": 1}}})

    def test_unknown_wiki_key(self):
        with self.assertRaisesRegex(config.ConfigError, "unknown key 'wiki.comment'"):
            _load({"wiki": {"enabled": False, "comment": "nope"}})


# Mirrors templates/config/interns.yml's shape and values -- the file the
# installer seeds a fresh consumer's .github/interns.yml from, and that
# resolve_agent_config() falls back to when the consumer's own file doesn't
# set a key. BuiltinTemplateIntegrationTests below loads the real file
# directly, to catch this fixture drifting from it.
_BUILTIN_FIXTURE = {
    "wiki": {"enabled": False},
    "checks": {"ignore": []},
    "defaults": {
        "model": "claude-sonnet-5",
        "max_turns": 60,
        "timeout_minutes": 20,
        "max_output_tokens": 32000,
        "cost_warn_usd": 2.0,
    },
    "agents": {
        "refiner": {
            "max_turns": 35,
            "disallowed_tools": ["Bash", "Task", "ScheduleWakeup", "WebSearch", "WebFetch", "Write", "Edit", "NotebookEdit"],
        },
        "estimator": {
            "max_turns": 30,
            "disallowed_tools": ["Bash", "Task", "ScheduleWakeup", "WebSearch", "WebFetch", "Write", "Edit", "NotebookEdit"],
        },
        "coder": {
            "max_turns": 75,
            "timeout_minutes": 30,
            "disallowed_tools": ["Task", "ScheduleWakeup", "WebSearch", "WebFetch", "NotebookEdit"],
        },
        "reviewer": {
            "max_turns": 45,
            "disallowed_tools": ["Task", "ScheduleWakeup", "WebSearch", "WebFetch", "Write", "Edit", "NotebookEdit"],
        },
    },
}


class ResolveAgentConfigTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("pipeline.config._builtin_data", return_value=_BUILTIN_FIXTURE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_agent_override_wins_over_defaults(self):
        data = {
            "defaults": {"max_turns": 40, "timeout_minutes": 30},
            "agents": {"coder": {"max_turns": 60, "timeout_minutes": 45}},
        }
        cfg = config.resolve_agent_config(data, "coder", "interns.yml")
        self.assertEqual(cfg.max_turns, 60)
        self.assertEqual(cfg.timeout_minutes, 45)

    def test_unset_agent_key_falls_back_to_defaults(self):
        data = {"defaults": {"model": "claude-sonnet-5", "max_output_tokens": 32000}, "agents": {"coder": {}}}
        cfg = config.resolve_agent_config(data, "coder", "interns.yml")
        self.assertEqual(cfg.model, "claude-sonnet-5")
        self.assertEqual(cfg.max_output_tokens, 32000)

    def test_missing_config_falls_back_to_builtin_defaults(self):
        cfg = config.resolve_agent_config({}, "reviewer", "interns.yml")
        self.assertEqual(cfg.model, "claude-sonnet-5")
        # reviewer's own built-in override (45), not the flat built-in
        # defaults.max_turns (60).
        self.assertEqual(cfg.max_turns, 45)

    def test_refiner_defaults_to_claude_sonnet_5(self):
        cfg = config.resolve_agent_config({}, "refiner", "interns.yml")
        self.assertEqual(cfg.model, "claude-sonnet-5")

    def test_wiki_disabled_by_default(self):
        cfg = config.resolve_agent_config({}, "coder", "interns.yml")
        self.assertFalse(cfg.wiki_enabled)
        self.assertEqual(cfg.wiki_repo, "")

    def test_wiki_enabled_surfaces_url(self):
        data = {"wiki": {"enabled": True, "url": "acme/widgets.wiki"}}
        cfg = config.resolve_agent_config(data, "coder", "interns.yml")
        self.assertTrue(cfg.wiki_enabled)
        self.assertEqual(cfg.wiki_repo, "acme/widgets.wiki")

    def test_wiki_enabled_without_url_is_rejected(self):
        data = {"wiki": {"enabled": True}}
        with self.assertRaisesRegex(config.ConfigError, "wiki.enabled is true but wiki.url is unset"):
            config.resolve_agent_config(data, "coder", "interns.yml")

    def test_unknown_agent_argument_is_rejected(self):
        with self.assertRaisesRegex(config.ConfigError, "unknown agent 'tester'"):
            config.resolve_agent_config({}, "tester", "interns.yml")

    def test_max_output_tokens_below_floor_is_rejected(self):
        data = {"defaults": {"max_output_tokens": 8000}}
        with self.assertRaisesRegex(config.ConfigError, "safety ceiling"):
            config.resolve_agent_config(data, "coder", "interns.yml")

    def test_non_positive_cost_warn_usd_is_rejected(self):
        data = {"defaults": {"cost_warn_usd": 0}}
        with self.assertRaises(config.ConfigError):
            config.resolve_agent_config(data, "coder", "interns.yml")

    def test_refiners_builtin_disallowed_tools_blocks_bash_and_task(self):
        cfg = config.resolve_agent_config({}, "refiner", "interns.yml")
        self.assertIn("Bash", cfg.disallowed_tools)
        self.assertIn("Task", cfg.disallowed_tools)

    def test_coders_builtin_disallowed_tools_does_not_block_bash_write_edit(self):
        cfg = config.resolve_agent_config({}, "coder", "interns.yml")
        self.assertNotIn("Bash", cfg.disallowed_tools)
        self.assertNotIn("Write", cfg.disallowed_tools)
        self.assertNotIn("Edit", cfg.disallowed_tools)
        self.assertIn("Task", cfg.disallowed_tools)

    def test_reviewers_builtin_disallowed_tools_does_not_block_bash(self):
        cfg = config.resolve_agent_config({}, "reviewer", "interns.yml")
        self.assertNotIn("Bash", cfg.disallowed_tools)

    def test_agent_disallowed_tools_overrides_the_builtin(self):
        data = {"agents": {"refiner": {"disallowed_tools": ["Bash", "Task"]}}}
        cfg = config.resolve_agent_config(data, "refiner", "interns.yml")
        self.assertEqual(cfg.disallowed_tools, ["Bash", "Task"])

    def test_disallowed_tools_that_is_not_a_list_is_rejected(self):
        data = {"agents": {"refiner": {"disallowed_tools": "Bash,Task"}}}
        with self.assertRaisesRegex(config.ConfigError, "must be a YAML list"):
            config.resolve_agent_config(data, "refiner", "interns.yml")


class BuiltinTemplateIntegrationTests(unittest.TestCase):
    """Loads the real templates/config/interns.yml (no mocking) -- catches
    the shipped template drifting from what resolve_agent_config() actually
    falls back to, and _BUILTIN_FIXTURE above drifting from the template."""

    def setUp(self):
        config._builtin_data.cache_clear()
        self.addCleanup(config._builtin_data.cache_clear)

    def test_real_template_matches_the_fixture(self):
        self.assertEqual(config._builtin_data(), _BUILTIN_FIXTURE)

    def test_coder_resolves_from_the_real_template_with_no_consumer_file(self):
        cfg = config.resolve_agent_config({}, "coder", "interns.yml")
        self.assertEqual(cfg.max_turns, 75)
        self.assertEqual(cfg.timeout_minutes, 30)
        self.assertNotIn("Bash", cfg.disallowed_tools)


class ChecksIgnoreTests(unittest.TestCase):
    def test_defaults_to_empty(self):
        self.assertEqual(config.checks_ignore({}, "interns.yml"), [])

    def test_reads_the_list(self):
        data = {"checks": {"ignore": ["preview-deploy"]}}
        self.assertEqual(config.checks_ignore(data, "interns.yml"), ["preview-deploy"])

    def test_non_list_value_is_rejected_not_silently_ignored(self):
        data = {"checks": {"ignore": "preview-deploy"}}
        with self.assertRaisesRegex(config.ConfigError, "checks.ignore must be a YAML list"):
            config.checks_ignore(data, "interns.yml")


class CliTests(unittest.TestCase):
    def test_agent_config_prints_key_value_lines(self):
        # No --config mock here: a nonexistent consumer file falls through to
        # the real shipped template via _builtin_data().
        with patch("builtins.print") as mock_print:
            config._main(["--config", "/nonexistent/interns.yml", "agent-config", "coder"])
        printed = [call.args[0] for call in mock_print.call_args_list]
        self.assertIn("model=claude-sonnet-5", printed)

    def test_checks_ignore_prints_json_array(self):
        data = {"checks": {"ignore": ["preview-deploy"]}}
        with patch("pipeline.config.load_raw", return_value=data), patch("builtins.print") as mock_print:
            config._main(["checks-ignore"])
        mock_print.assert_any_call('["preview-deploy"]')

    def test_config_error_exits_non_zero(self):
        with patch("pipeline.config.load_raw", side_effect=config.ConfigError("boom")):
            self.assertEqual(config._main(["agent-config", "tester"]), 1)


if __name__ == "__main__":
    unittest.main()
