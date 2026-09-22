import os
import unittest
from unittest.mock import patch

from interns import cli
from interns.ctx import ActionsCtx


class FromEnvTests(unittest.TestCase):
    def _env(self, **extra):
        return patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "acme/widgets",
            "GH_TOKEN": "tok",
            "GITHUB_SERVER_URL": "https://github.com",
            **extra,
        }, clear=True)

    def test_builds_from_standard_actions_env(self):
        with self._env(GITHUB_RUN_ID="123", REVIEWER_BOT="reviewer[bot]"):
            ctx = ActionsCtx.from_env()
        self.assertEqual(ctx.repo, "acme/widgets")
        self.assertEqual(ctx.token, "tok")
        self.assertEqual(ctx.server_url, "https://github.com")
        self.assertEqual(ctx.run_id, "123")
        self.assertEqual(ctx.reviewer_bot, "reviewer[bot]")

    def test_optional_fields_default_when_absent(self):
        with self._env():
            ctx = ActionsCtx.from_env()
        self.assertEqual(ctx.run_id, "")
        self.assertEqual(ctx.run_attempt, 1)
        self.assertEqual(ctx.workspace, ".")
        self.assertEqual(ctx.event_name, "")
        self.assertEqual(ctx.reviewer_bot, "")
        self.assertEqual(ctx.step_summary, "")

    def test_missing_repo_raises(self):
        with patch.dict(os.environ, {"GH_TOKEN": "x", "GITHUB_SERVER_URL": "https://github.com"}, clear=True):
            with self.assertRaises(cli.MissingEnvError):
                ActionsCtx.from_env()

    def test_missing_token_raises(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets", "GITHUB_SERVER_URL": "https://github.com"}, clear=True):
            with self.assertRaises(cli.MissingEnvError):
                ActionsCtx.from_env()

    def test_missing_server_url_raises(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets", "GH_TOKEN": "x"}, clear=True):
            with self.assertRaises(cli.MissingEnvError):
                ActionsCtx.from_env()


class UrlMethodTests(unittest.TestCase):
    def _ctx(self, **kw):
        defaults = dict(repo="acme/widgets", token="", server_url="https://github.com",
                        run_id="42", run_attempt=1, workspace=".", event_name="",
                        reviewer_bot="", step_summary="")
        defaults.update(kw)
        return ActionsCtx(**defaults)

    def test_run_url(self):
        self.assertEqual(
            self._ctx().run_url(),
            "https://github.com/acme/widgets/actions/runs/42",
        )

    def test_pr_url(self):
        self.assertEqual(
            self._ctx().pr_url(12),
            "https://github.com/acme/widgets/pull/12",
        )

    def test_explicit_server_url(self):
        ctx = self._ctx(server_url="https://ghe.example.com")
        self.assertEqual(ctx.pr_url(12), "https://ghe.example.com/acme/widgets/pull/12")


if __name__ == "__main__":
    unittest.main()
