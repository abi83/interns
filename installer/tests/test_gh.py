import unittest
from unittest import mock

from interns_install import gh


class ScopeParseTests(unittest.TestCase):
    def test_parse_scopes(self):
        text = "  - Token scopes: 'gist', 'read:org', 'repo'\n"
        self.assertEqual(gh._parse_scopes(text), {"gist", "read:org", "repo"})

    def test_no_scopes_line(self):
        self.assertEqual(gh._parse_scopes("Logged in to github.com"), set())


class SecretVerbTests(unittest.TestCase):
    def test_verb(self):
        self.assertEqual(gh.secret_verb("A", None), "set")
        self.assertEqual(gh.secret_verb("A", []), "add")
        self.assertEqual(gh.secret_verb("A", ["A"]), "overwrite")


class DefaultBranchTests(unittest.TestCase):
    def test_reads_default_branch(self):
        with mock.patch.object(gh, "api", return_value={"default_branch": "trunk"}):
            self.assertEqual(gh.default_branch("acme/widgets"), "trunk")

    def test_falls_back_to_main_on_unexpected_shape(self):
        with mock.patch.object(gh, "api", return_value=None):
            self.assertEqual(gh.default_branch("acme/widgets"), "main")


if __name__ == "__main__":
    unittest.main()
