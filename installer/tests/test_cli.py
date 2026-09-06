import unittest
from unittest import mock

from interns_install import cli, gh
from interns_install.cli import _add_wrapper, _parse_args, _secret_verb
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


class SecretVerbTests(unittest.TestCase):
    def test_verb(self):
        self.assertEqual(_secret_verb("A", None), "set")
        self.assertEqual(_secret_verb("A", []), "add")
        self.assertEqual(_secret_verb("A", ["A"]), "overwrite")


class ScopeParseTests(unittest.TestCase):
    def test_parse_scopes(self):
        text = "  - Token scopes: 'gist', 'read:org', 'repo'\n"
        self.assertEqual(gh._parse_scopes(text), {"gist", "read:org", "repo"})

    def test_no_scopes_line(self):
        self.assertEqual(gh._parse_scopes("Logged in to github.com"), set())


class AddWrapperTests(unittest.TestCase):
    def _repo(self):
        return gh.Repo(owner="acme", name="widgets", is_org=False)

    def test_opens_pr_and_records_manual_followup(self):
        con = Console(assume_yes=True)
        with mock.patch.multiple(
            cli.gh,
            get_file=mock.DEFAULT, branch_head_sha=mock.DEFAULT,
            create_branch=mock.DEFAULT, put_file=mock.DEFAULT, create_pr=mock.DEFAULT,
        ) as m:
            m["get_file"].return_value = "name: Install interns\n"
            m["branch_head_sha"].return_value = "abc123"
            m["create_pr"].return_value = "https://github.com/acme/widgets/pull/7"
            with mock.patch.object(cli, "_default_branch", return_value="main"):
                _add_wrapper(con, self._repo())

        m["get_file"].assert_called_once_with(
            cli.INTERNS_REPO, "templates/workflows/install.yml", cli.INTERNS_REF)
        m["put_file"].assert_called_once()
        self.assertTrue(any("pull/7" in note for note in con.manual))

    def test_dry_run_makes_no_calls(self):
        con = Console(assume_yes=True, dry_run=True)
        with mock.patch.object(cli.gh, "get_file") as get_file:
            _add_wrapper(con, self._repo())
        get_file.assert_not_called()
        self.assertTrue(con.manual)


if __name__ == "__main__":
    unittest.main()
