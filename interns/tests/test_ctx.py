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
        with self._env():
            ctx = ActionsCtx.from_env()
        self.assertEqual(ctx.repo, "acme/widgets")
        self.assertEqual(ctx.token, "tok")
        self.assertEqual(ctx.server_url, "https://github.com")

    def test_run_scoped_values_are_read_lazily_from_env(self):
        extra = dict(GITHUB_RUN_ATTEMPT="2", GITHUB_WORKSPACE="/w", GITHUB_STEP_SUMMARY="/s", GITHUB_EVENT_NAME="push")
        with self._env(GITHUB_RUN_ID="9", REVIEWER_BOT="bot", **extra):
            ctx = ActionsCtx.from_env()
            self.assertEqual(
                (ctx.run_id, ctx.run_attempt, ctx.workspace, ctx.step_summary, ctx.reviewer_bot, ctx.event_name),
                ("9", 2, "/w", "/s", "bot", "push"),
            )

    def test_construction_does_not_require_run_scoped_env(self):
        with self._env():
            ActionsCtx.from_env()

    def test_each_required_accessor_raises_when_unset(self):
        with self._env():
            ctx = ActionsCtx.from_env()
            for name in ("run_id", "run_attempt", "workspace", "reviewer_bot", "step_summary", "run_url"):
                with self.subTest(name=name), self.assertRaises(cli.MissingEnvError):
                    getattr(ctx, name) if name != "run_url" else ctx.run_url()

    def test_event_name_is_optional(self):
        with self._env():
            self.assertEqual(ActionsCtx.from_env().event_name, "")

    def test_missing_repo_raises(self):
        with patch.dict(os.environ, {"GH_TOKEN": "x", "GITHUB_SERVER_URL": "https://github.com"}, clear=True), self.assertRaises(cli.MissingEnvError):
            ActionsCtx.from_env()

    def test_missing_token_raises(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets", "GITHUB_SERVER_URL": "https://github.com"}, clear=True), self.assertRaises(cli.MissingEnvError):
            ActionsCtx.from_env()

    def test_missing_server_url_raises(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets", "GH_TOKEN": "x"}, clear=True), self.assertRaises(cli.MissingEnvError):
            ActionsCtx.from_env()


class UrlMethodTests(unittest.TestCase):
    def _ctx(self, **kw):
        defaults = dict(repo="acme/widgets", token="", server_url="https://github.com")
        defaults.update(kw)
        return ActionsCtx(**defaults)

    def test_run_url(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "42"}):
            self.assertEqual(
                self._ctx().run_url(),
                "https://github.com/acme/widgets/actions/runs/42",
            )

    def test_pr_url(self):
        self.assertEqual(
            self._ctx().pr_url(12),
            "https://github.com/acme/widgets/pull/12",
        )

    def test_config_path_defaults_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self._ctx().config_path, ".github/interns.yml")

    def test_config_path_honours_override(self):
        with patch.dict(os.environ, {"INTERNS_CONFIG": "custom.yml"}):
            self.assertEqual(self._ctx().config_path, "custom.yml")

    def test_explicit_server_url(self):
        ctx = self._ctx(server_url="https://ghe.example.com")
        self.assertEqual(ctx.pr_url(12), "https://ghe.example.com/acme/widgets/pull/12")


if __name__ == "__main__":
    unittest.main()
