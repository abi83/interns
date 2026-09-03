import unittest

from interns_install import gh
from interns_install.cli import _parse_args, _secret_verb


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


if __name__ == "__main__":
    unittest.main()
