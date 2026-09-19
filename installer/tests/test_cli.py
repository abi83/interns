import unittest
from unittest import mock

from interns_install import cli, gh, install_files
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
        self.assertEqual(a.issue_templates, "false")
        self.assertFalse(a.skip_handoff)

    def test_issue_templates_bare_flag(self):
        self.assertEqual(_parse_args(["--issue-templates"]).issue_templates, "true")
        self.assertEqual(_parse_args(["--issue-templates=true"]).issue_templates, "true")

    def test_repo_and_dry_run(self):
        a = _parse_args(["--repo", "acme/widgets", "--dry-run", "--yes"])
        self.assertEqual(a.repo, "acme/widgets")
        self.assertTrue(a.dry_run)
        self.assertTrue(a.yes)


class WorkflowScopePreflightTests(unittest.TestCase):
    def _con(self):
        return Console(assume_yes=True, dry_run=False)

    def test_classic_token_without_workflow_exits(self):
        with mock.patch.object(gh, "auth_scopes", return_value={"repo"}):
            with self.assertRaises(SystemExit):
                cli._workflow_scope_preflight(self._con())

    def test_classic_token_with_workflow_passes(self):
        with mock.patch.object(gh, "auth_scopes", return_value={"repo", "workflow"}):
            cli._workflow_scope_preflight(self._con())

    def test_fine_grained_pat_falls_through(self):
        with mock.patch.object(gh, "auth_scopes", return_value=set()):
            cli._workflow_scope_preflight(self._con())


def _repo():
    return gh.Repo(owner="acme", name="widgets", is_org=False)


class WriteOAuthTokenTests(unittest.TestCase):
    def test_opens_claude_app_install_page_and_notes_manual_reminder(self):
        con = Console(assume_yes=False)
        con.prompt_secret = lambda q: ""
        with mock.patch.object(cli.webbrowser, "open") as opener:
            _write_oauth_token(con, _repo(), existing_secrets=[])
        opener.assert_called_once_with("https://github.com/apps/claude/installations/new")
        self.assertTrue(any("Claude Code GitHub App" in n for n in con.manual))

    def test_skips_browser_under_yes(self):
        con = Console(assume_yes=True)
        con.prompt_secret = lambda q: ""
        with mock.patch.object(cli.webbrowser, "open") as opener:
            _write_oauth_token(con, _repo(), existing_secrets=[])
        opener.assert_not_called()
        self.assertTrue(any("Claude Code GitHub App" in n for n in con.manual))

    def test_dry_run_records_planned_secret_without_prompting(self):
        con = Console(assume_yes=False, dry_run=True)
        with mock.patch.object(cli.webbrowser, "open") as opener:
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
        return gh.Repo(owner="acme", name="widgets", is_org=False)

    def test_opens_one_pr_for_all_missing_files(self):
        con = Console(assume_yes=True)
        with mock.patch.object(install_files, "collect_missing_files",
                               return_value={".github/interns.yml": ("cfg", None)}), \
             mock.patch.multiple(
                 cli.gh,
                 branch_head_sha=mock.DEFAULT, create_branch=mock.DEFAULT,
                 put_file=mock.DEFAULT, create_pr=mock.DEFAULT) as m:
            m["branch_head_sha"].return_value = "abc123"
            m["create_pr"].return_value = "https://github.com/acme/widgets/pull/7"
            url = _stage_install_files(con, self._repo(), "main", issue_templates=False)

        self.assertEqual(url, "https://github.com/acme/widgets/pull/7")
        m["put_file"].assert_called_once_with(
            "acme/widgets", ".github/interns.yml", "cfg",
            "chore: install interns pipeline caller stubs", mock.ANY,
            sha=None)
        m["create_pr"].assert_called_once()

    def test_stale_file_is_updated_with_its_sha(self):
        con = Console(assume_yes=True)
        with mock.patch.object(install_files, "collect_missing_files",
                               return_value={".github/workflows/install.yml": ("new", "sha-old")}), \
             mock.patch.multiple(
                 cli.gh,
                 branch_head_sha=mock.DEFAULT, create_branch=mock.DEFAULT,
                 put_file=mock.DEFAULT, create_pr=mock.DEFAULT) as m:
            m["branch_head_sha"].return_value = "abc123"
            m["create_pr"].return_value = "https://github.com/acme/widgets/pull/8"
            _stage_install_files(con, self._repo(), "main", issue_templates=False)

        _, kwargs = m["put_file"].call_args
        self.assertEqual(kwargs["sha"], "sha-old")

    def test_returns_none_when_nothing_missing(self):
        con = Console(assume_yes=True)
        with mock.patch.object(install_files, "collect_missing_files", return_value={}), \
             mock.patch.object(cli.gh, "create_pr") as create_pr:
            url = _stage_install_files(con, self._repo(), "main", issue_templates=False)
        self.assertIsNone(url)
        create_pr.assert_not_called()

    def test_dry_run_makes_no_calls(self):
        con = Console(assume_yes=True, dry_run=True)
        with mock.patch.object(install_files, "collect_missing_files") as collect:
            _stage_install_files(con, self._repo(), "main", issue_templates=False)
        collect.assert_not_called()
        self.assertTrue(con.manual)


if __name__ == "__main__":
    unittest.main()
