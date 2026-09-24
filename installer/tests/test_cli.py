import unittest
from unittest import mock

from interns import gh
from interns_install import apps, cli, gh_admin, install_files, safety
from interns_install.cli import (
    _parse_args,
    _stage_install_files,
    _write_oauth_token,
)
from interns_install.console import Console


class ArgTests(unittest.TestCase):
    def test_defaults(self):
        a = _parse_args([])
        self.assertIsNone(a.repo)
        self.assertFalse(a.yes)
        self.assertFalse(a.dry_run)
        self.assertFalse(a.issue_templates)
        self.assertFalse(a.skip_handoff)

    def test_issue_templates_bare_flag(self):
        self.assertTrue(_parse_args(["--issue-templates"]).issue_templates)

    def test_repo_and_dry_run(self):
        a = _parse_args(["--repo", "acme/widgets", "--dry-run", "--yes"])
        self.assertEqual(a.repo, "acme/widgets")
        self.assertTrue(a.dry_run)
        self.assertTrue(a.yes)


class WorkflowScopePreflightTests(unittest.TestCase):
    def _con(self):
        return Console(assume_yes=True, dry_run=False)

    def test_classic_token_without_workflow_fails(self):
        with mock.patch.object(gh_admin, "auth_scopes", return_value={"repo"}):
            self.assertFalse(cli._workflow_scope_ok(self._con()))

    def test_classic_token_with_workflow_passes(self):
        with mock.patch.object(gh_admin, "auth_scopes", return_value={"repo", "workflow"}):
            self.assertTrue(cli._workflow_scope_ok(self._con()))

    def test_fine_grained_pat_falls_through(self):
        with mock.patch.object(gh_admin, "auth_scopes", return_value=set()):
            self.assertTrue(cli._workflow_scope_ok(self._con()))


class SecretsScopeTests(unittest.TestCase):
    def test_listable_secrets_pass(self):
        self.assertTrue(cli._secrets_scope_ok(Console(assume_yes=False), []))

    def test_unlistable_secrets_follow_the_confirmation(self):
        con = Console(assume_yes=False)
        con.confirm = lambda q, default=False: False
        self.assertFalse(cli._secrets_scope_ok(con, None))
        con.confirm = lambda q, default=False: True
        self.assertTrue(cli._secrets_scope_ok(con, None))


class _Both:
    """Enters two `patch.multiple` contexts and merges their mocks."""

    def __init__(self, *patchers):
        self._patchers = patchers

    def __enter__(self):
        mocks = {}
        for patcher in self._patchers:
            mocks.update(patcher.__enter__())
        return mocks

    def __exit__(self, *exc):
        for patcher in reversed(self._patchers):
            patcher.__exit__(*exc)


def _repo():
    return gh_admin.Repo(owner="acme", name="widgets", is_org=False)


class WriteOAuthTokenTests(unittest.TestCase):
    def test_opens_claude_app_install_page_and_notes_manual_reminder(self):
        con = Console(assume_yes=False)
        with mock.patch("interns_install.credentials.prompt_secret", return_value=""), \
             mock.patch.object(apps.webbrowser, "open") as opener:
            _write_oauth_token(con, _repo(), existing_secrets=[])
        opener.assert_called_once_with("https://github.com/apps/claude/installations/new")
        self.assertTrue(any("Claude Code GitHub App" in n for n in con.manual))

    def test_skips_browser_under_yes(self):
        con = Console(assume_yes=True)
        with mock.patch("interns_install.credentials.prompt_secret", return_value=""), \
             mock.patch.object(apps.webbrowser, "open") as opener:
            _write_oauth_token(con, _repo(), existing_secrets=[])
        opener.assert_not_called()
        self.assertTrue(any("Claude Code GitHub App" in n for n in con.manual))

    def test_dry_run_records_planned_secret_without_prompting(self):
        con = Console(assume_yes=False, dry_run=True)
        with mock.patch.object(apps.webbrowser, "open") as opener:
            _write_oauth_token(con, _repo(), existing_secrets=[])
        opener.assert_not_called()
        self.assertTrue(any("CLAUDE_CODE_OAUTH_TOKEN" in p for p in con.planned))


class AppClientIdArgTests(unittest.TestCase):
    def test_client_id_flags_parse(self):
        a = _parse_args(["--coder-client-id", "Iv1.aaa", "--reviewer-client-id", "Iv1.bbb"])
        self.assertEqual(a.coder_client_id, "Iv1.aaa")
        self.assertEqual(a.reviewer_client_id, "Iv1.bbb")

    def test_client_id_flags_default_none(self):
        a = _parse_args([])
        self.assertIsNone(a.coder_client_id)
        self.assertIsNone(a.reviewer_client_id)


class StageInstallFilesTests(unittest.TestCase):
    def _repo(self):
        return gh_admin.Repo(owner="acme", name="widgets", is_org=False)

    def test_opens_one_pr_for_all_missing_files(self):
        con = Console(assume_yes=True)
        with mock.patch.object(install_files, "collect_missing_files",
                               return_value={".github/interns.yml": ("cfg", None)}), \
             mock.patch.multiple(
                 cli.gh_admin,
                 branch_head_sha=mock.DEFAULT, create_branch=mock.DEFAULT,
                 put_file=mock.DEFAULT) as m, \
             mock.patch.object(cli.gh, "pr_create") as pr_create:
            m["pr_create"] = pr_create
            m["branch_head_sha"].return_value = "abc123"
            m["pr_create"].return_value = "https://github.com/acme/widgets/pull/7"
            url = _stage_install_files(con, self._repo(), "main", issue_templates=False)

        self.assertEqual(url, "https://github.com/acme/widgets/pull/7")
        m["put_file"].assert_called_once_with(
            "acme/widgets", ".github/interns.yml", "cfg",
            "chore: install interns pipeline caller stubs", mock.ANY,
            sha=None)
        m["pr_create"].assert_called_once()

    def test_stale_file_is_updated_with_its_sha(self):
        con = Console(assume_yes=True)
        with mock.patch.object(install_files, "collect_missing_files",
                               return_value={".github/workflows/install.yml": ("new", "sha-old")}), \
             mock.patch.multiple(
                 cli.gh_admin,
                 branch_head_sha=mock.DEFAULT, create_branch=mock.DEFAULT,
                 put_file=mock.DEFAULT) as m, \
             mock.patch.object(cli.gh, "pr_create") as pr_create:
            m["pr_create"] = pr_create
            m["branch_head_sha"].return_value = "abc123"
            m["pr_create"].return_value = "https://github.com/acme/widgets/pull/8"
            _stage_install_files(con, self._repo(), "main", issue_templates=False)

        _, kwargs = m["put_file"].call_args
        self.assertEqual(kwargs["sha"], "sha-old")

    def test_returns_none_when_nothing_missing(self):
        con = Console(assume_yes=True)
        with mock.patch.object(install_files, "collect_missing_files", return_value={}), \
             mock.patch.object(cli.gh, "pr_create") as pr_create:
            url = _stage_install_files(con, self._repo(), "main", issue_templates=False)
        self.assertIsNone(url)
        pr_create.assert_not_called()

    def test_dry_run_makes_no_calls(self):
        con = Console(assume_yes=True, dry_run=True)
        with mock.patch.object(install_files, "collect_missing_files") as collect:
            _stage_install_files(con, self._repo(), "main", issue_templates=False)
        collect.assert_not_called()
        self.assertTrue(con.manual)


class HandoffTests(unittest.TestCase):
    def _args(self, **kw):
        return _parse_args([f"--{k.replace('_', '-')}={v}" for k, v in kw.items()])

    def _run(self, con, pr_url=None, **args):
        with mock.patch.object(cli.gh, "default_branch", return_value="main"), \
             mock.patch.object(cli, "_stage_install_files", return_value=pr_url), \
             mock.patch.object(cli.gh, "dispatch_workflow") as dispatch:
            cli._handoff(con, _repo(), self._args(**args))
        return dispatch

    def test_open_pr_defers_dispatch_to_manual_step(self):
        con = Console(assume_yes=True)
        dispatch = self._run(con, pr_url="https://example/pr/1")
        dispatch.assert_not_called()
        self.assertTrue(any("https://example/pr/1" in n for n in con.manual))

    def test_dispatches_on_default_branch(self):
        dispatch = self._run(Console(assume_yes=True))
        dispatch.assert_called_once_with("acme/widgets", cli.WORKFLOW, "main", {})

    def test_dispatches_on_handoff_ref(self):
        dispatch = self._run(Console(assume_yes=True), handoff_ref="v1")
        dispatch.assert_called_once_with("acme/widgets", cli.WORKFLOW, "v1", {})

    def test_declined_dispatch_records_manual_command(self):
        con = Console(assume_yes=False)
        con.confirm = lambda q, default=False: False
        dispatch = self._run(con)
        dispatch.assert_not_called()
        self.assertTrue(any("gh workflow run" in n for n in con.manual))

    def test_dry_run_does_not_dispatch(self):
        dispatch = self._run(Console(assume_yes=True, dry_run=True))
        dispatch.assert_not_called()


class StageDeclineTests(unittest.TestCase):
    def test_declined_pr_records_manual_step(self):
        con = Console(assume_yes=False)
        con.confirm = lambda q, default=False: False
        with mock.patch.object(install_files, "collect_missing_files",
                               return_value={"a.yml": ("x", None), "b.yml": ("y", "sha")}), \
             mock.patch.object(cli.gh, "pr_create") as pr_create:
            url = _stage_install_files(con, _repo(), "main", issue_templates=False)
        self.assertIsNone(url)
        pr_create.assert_not_called()
        self.assertTrue(con.manual)


class MainTests(unittest.TestCase):
    """End-to-end tests for main()'s wiring: argument parsing through to exit
    code, with gh/safety/apps mocked at their module boundary so each branch
    of the try/except structure in main() is exercised on its own."""

    def _patch_happy_path(self):
        """Patches every collaborator main() calls so a full run succeeds;
        each test overrides one to force a specific exit path."""
        admin = mock.patch.multiple(
            cli.gh_admin,
            ensure_available=mock.DEFAULT,
            current_repo=mock.DEFAULT,
            auth_scopes=mock.DEFAULT,
        )
        shared = mock.patch.multiple(
            cli.gh,
            list_secret_names=mock.DEFAULT,
            default_branch=mock.DEFAULT,
        )
        return _Both(admin, shared)

    def test_success_path_returns_zero(self):
        with self._patch_happy_path() as m, \
             mock.patch.object(cli.safety, "check_branch_protection"), \
             mock.patch.object(cli.safety, "check_pages"), \
             mock.patch.object(cli.safety, "check_metrics_branch"), \
             mock.patch.object(cli.safety, "check_dashboard"), \
             mock.patch.object(cli, "provision_app"), \
             mock.patch.object(cli, "_write_oauth_token"), \
             mock.patch.object(cli, "_handoff"):
            m["current_repo"].return_value = _repo()
            m["auth_scopes"].return_value = {"repo", "workflow"}
            m["list_secret_names"].return_value = []
            m["default_branch"].return_value = "main"
            code = cli.main(["--yes"])
        self.assertEqual(code, 0)

    def test_gh_not_available_exits_one_without_summary(self):
        with mock.patch.object(cli.gh_admin, "ensure_available", side_effect=gh.GhError("gh not on PATH")), \
             mock.patch.object(Console, "summary") as summary:
            code = cli.main(["--yes"])
        self.assertEqual(code, 1)
        summary.assert_not_called()

    def test_current_repo_failure_exits_one_without_summary(self):
        with mock.patch.object(cli.gh_admin, "ensure_available"), \
             mock.patch.object(cli.gh_admin, "current_repo", side_effect=gh.GhError("no repo here")), \
             mock.patch.object(Console, "summary") as summary:
            code = cli.main(["--yes"])
        self.assertEqual(code, 1)
        summary.assert_not_called()

    def test_safety_check_gh_error_exits_one_with_summary(self):
        with self._patch_happy_path() as m, \
             mock.patch.object(cli.safety, "check_branch_protection",
                               side_effect=gh.GhError("could not read protection")), \
             mock.patch.object(Console, "summary") as summary:
            m["current_repo"].return_value = _repo()
            m["auth_scopes"].return_value = {"repo", "workflow"}
            m["list_secret_names"].return_value = []
            m["default_branch"].return_value = "main"
            code = cli.main(["--yes"])
        self.assertEqual(code, 1)
        summary.assert_called_once()

    def test_safety_check_error_exits_one_with_summary(self):
        with self._patch_happy_path() as m, \
             mock.patch.object(cli.safety, "check_branch_protection"), \
             mock.patch.object(cli.safety, "check_pages",
                               side_effect=safety.SafetyCheckError("Pages is public")), \
             mock.patch.object(Console, "summary") as summary:
            m["current_repo"].return_value = _repo()
            m["auth_scopes"].return_value = {"repo", "workflow"}
            m["list_secret_names"].return_value = []
            m["default_branch"].return_value = "main"
            code = cli.main(["--yes"])
        self.assertEqual(code, 1)
        summary.assert_called_once()

    def test_provisioning_gh_error_exits_one_with_summary(self):
        with self._patch_happy_path() as m, \
             mock.patch.object(cli.safety, "check_branch_protection"), \
             mock.patch.object(cli.safety, "check_pages"), \
             mock.patch.object(cli.safety, "check_metrics_branch"), \
             mock.patch.object(cli, "provision_app", side_effect=gh.GhError("mint failed")), \
             mock.patch.object(Console, "summary") as summary:
            m["current_repo"].return_value = _repo()
            m["auth_scopes"].return_value = {"repo", "workflow"}
            m["list_secret_names"].return_value = []
            m["default_branch"].return_value = "main"
            code = cli.main(["--yes"])
        self.assertEqual(code, 1)
        summary.assert_called_once()

    def test_provisioning_timeout_exits_one_with_summary(self):
        with self._patch_happy_path() as m, \
             mock.patch.object(cli.safety, "check_branch_protection"), \
             mock.patch.object(cli.safety, "check_pages"), \
             mock.patch.object(cli.safety, "check_metrics_branch"), \
             mock.patch.object(cli, "provision_app", side_effect=TimeoutError("callback never arrived")), \
             mock.patch.object(Console, "summary") as summary:
            m["current_repo"].return_value = _repo()
            m["auth_scopes"].return_value = {"repo", "workflow"}
            m["list_secret_names"].return_value = []
            m["default_branch"].return_value = "main"
            code = cli.main(["--yes"])
        self.assertEqual(code, 1)
        summary.assert_called_once()

    def test_skip_handoff_does_not_run_workflow_preflight_or_handoff(self):
        with self._patch_happy_path() as m, \
             mock.patch.object(cli.safety, "check_branch_protection"), \
             mock.patch.object(cli.safety, "check_pages"), \
             mock.patch.object(cli.safety, "check_metrics_branch"), \
             mock.patch.object(cli.safety, "check_dashboard"), \
             mock.patch.object(cli, "provision_app"), \
             mock.patch.object(cli, "_write_oauth_token"), \
             mock.patch.object(cli, "_handoff") as handoff:
            m["current_repo"].return_value = _repo()
            m["list_secret_names"].return_value = []
            m["default_branch"].return_value = "main"
            code = cli.main(["--yes", "--skip-handoff"])
        self.assertEqual(code, 0)
        m["auth_scopes"].assert_not_called()
        handoff.assert_not_called()


if __name__ == "__main__":
    unittest.main()
