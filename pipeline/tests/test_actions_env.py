import unittest
from unittest.mock import patch

from pipeline import actions_env


class RunUrlTests(unittest.TestCase):
    def test_builds_the_run_url_from_actions_env(self):
        with patch.dict("os.environ", {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_RUN_ID": "123"}):
            self.assertEqual(actions_env.run_url("acme/widgets"), "https://github.com/acme/widgets/actions/runs/123")


class PrUrlTests(unittest.TestCase):
    def test_builds_the_pr_url_from_actions_env(self):
        with patch.dict("os.environ", {"GITHUB_SERVER_URL": "https://github.com"}):
            self.assertEqual(actions_env.pr_url("acme/widgets", 12), "https://github.com/acme/widgets/pull/12")

    def test_explicit_server_url_overrides_the_env_and_needs_no_env_var(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                actions_env.pr_url("acme/widgets", 12, server_url="https://ghe.example.com"),
                "https://ghe.example.com/acme/widgets/pull/12",
            )
