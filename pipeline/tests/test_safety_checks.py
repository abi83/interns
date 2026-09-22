import io
import unittest
from unittest.mock import patch

from pipeline import cli, gh, safety_checks
from testkit.harness import default_ctx

SECRETS = safety_checks.DEFAULT_REQUIRED_SECRETS
VARS = safety_checks.DEFAULT_REQUIRED_VARS


class CheckSecretsTests(unittest.TestCase):
    def test_passes_when_all_present(self):
        with patch("pipeline.safety_checks.gh.list_secret_names", return_value=SECRETS):
            self.assertEqual(safety_checks.check_secrets("acme/widgets", SECRETS), [])

    def test_names_a_missing_secret(self):
        with patch("pipeline.safety_checks.gh.list_secret_names", return_value=[SECRETS[0]]):
            failures = safety_checks.check_secrets("acme/widgets", SECRETS)
        self.assertEqual(len(failures), 1)
        self.assertIn(f"missing repo secret(s): {' '.join(SECRETS[1:])}", failures[0])

    def test_warns_but_does_not_fail_when_secrets_cant_be_listed(self):
        with patch("pipeline.safety_checks.gh.list_secret_names", side_effect=gh.GhCommandError("403")), \
             patch("sys.stderr", io.StringIO()):
            self.assertEqual(safety_checks.check_secrets("acme/widgets", SECRETS), [])


class CheckVarsTests(unittest.TestCase):
    def test_names_a_missing_variable(self):
        with patch("pipeline.safety_checks.gh.list_variable_names", return_value=[VARS[0]]):
            failures = safety_checks.check_vars("acme/widgets", VARS)
        self.assertEqual(len(failures), 1)
        self.assertIn(f"missing repo variable(s): {' '.join(VARS[1:])}", failures[0])

    def test_warns_but_does_not_fail_when_variables_cant_be_listed(self):
        with patch("pipeline.safety_checks.gh.list_variable_names", side_effect=gh.GhCommandError("403")), \
             patch("sys.stderr", io.StringIO()):
            self.assertEqual(safety_checks.check_vars("acme/widgets", VARS), [])


class MainTests(unittest.TestCase):
    def _ctx(self, **kwargs):
        return default_ctx(token="x", **kwargs)

    def test_reports_every_failure_not_just_the_first(self):
        with patch("pipeline.safety_checks.gh.list_secret_names", return_value=[]), \
             patch("pipeline.safety_checks.gh.list_variable_names", return_value=[]):
            status = safety_checks._main(self._ctx(), [])
        self.assertEqual(status, 1)

    def test_all_pass_returns_zero(self):
        with patch("pipeline.safety_checks.gh.list_secret_names", return_value=SECRETS), \
             patch("pipeline.safety_checks.gh.list_variable_names", return_value=VARS):
            status = safety_checks._main(self._ctx(), [])
        self.assertEqual(status, 0)

    def test_fails_when_gh_token_unset(self):
        import os
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}, clear=True):
            with self.assertRaises(cli.MissingEnvError):
                from pipeline.ctx import ActionsCtx as _Ctx
                _Ctx.from_env()


if __name__ == "__main__":
    unittest.main()
