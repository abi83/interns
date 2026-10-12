import io
import os
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from interns import entrypoint


class DispatchTests(unittest.TestCase):
    def _run(self, argv, env):
        err = io.StringIO()
        with patch.dict(os.environ, env, clear=True), redirect_stderr(err):
            return entrypoint.main(argv), err.getvalue()

    def test_no_command_is_a_usage_error(self):
        status, err = self._run([], {})
        self.assertEqual(status, 2)
        self.assertIn("no command given", err)

    def test_unknown_command_lists_ctx_and_env_free_commands(self):
        status, err = self._run(["nope"], {})
        self.assertEqual(status, 2)
        self.assertIn("labels", err)
        self.assertIn("run-setup", err)

    def test_ctx_command_without_github_env_exits_1(self):
        status, err = self._run(["fetch-issue", "--issue", "1"], {})
        self.assertEqual(status, 1)
        self.assertIn("GITHUB_REPOSITORY unset", err)

    def test_env_free_command_runs_without_github_env(self):
        with patch.dict(entrypoint._ENV_FREE_COMMANDS, {"prompt": lambda argv: 7}):
            status, _ = self._run(["prompt", "a.md"], {})
        self.assertEqual(status, 7)

    def test_env_free_command_missing_env_exits_1(self):
        def needs_env(argv):
            entrypoint.cli.require_env("NOPE_X")

        with patch.dict(entrypoint._ENV_FREE_COMMANDS, {"prompt": needs_env}):
            status, err = self._run(["prompt"], {})
        self.assertEqual(status, 1)
        self.assertIn("NOPE_X unset", err)


if __name__ == "__main__":
    unittest.main()
