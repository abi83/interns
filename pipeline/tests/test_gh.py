import json
import subprocess
import unittest
from unittest.mock import patch

from pipeline import gh


def _proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr)


class RunTests(unittest.TestCase):
    def test_gh_not_installed(self):
        with patch("pipeline.gh.subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(gh.GhNotInstalledError):
                gh._run(["auth", "status"])

    def test_command_failure_raises_with_stderr(self):
        exc = subprocess.CalledProcessError(1, ["gh", "issue", "view", "1"], output="", stderr="not found")
        with patch("pipeline.gh.subprocess.run", side_effect=exc):
            with self.assertRaisesRegex(gh.GhCommandError, "not found"):
                gh._run(["issue", "view", "1"])

    def test_success_returns_completed_process(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="ok")) as mock_run:
            result = gh._run(["auth", "status"])
        self.assertEqual(result.stdout, "ok")
        self.assertEqual(mock_run.call_args[0][0], ["gh", "auth", "status"])


class ScopeParseTests(unittest.TestCase):
    def test_parse_scopes(self):
        text = "  - Token scopes: 'gist', 'read:org', 'repo'\n"
        self.assertEqual(gh._parse_scopes(text), {"gist", "read:org", "repo"})

    def test_no_scopes_line(self):
        self.assertEqual(gh._parse_scopes("Logged in to github.com"), set())


class ApiTests(unittest.TestCase):
    def test_get_parses_json_body(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout='{"a": 1}')) as mock_run:
            result = gh.api("repos/acme/widgets")
        self.assertEqual(result, {"a": 1})
        args = mock_run.call_args[0][0]
        self.assertIn("repos/acme/widgets", args)
        self.assertIn("GET", args)

    def test_empty_body_returns_none(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="")):
            self.assertIsNone(gh.api("repos/acme/widgets"))

    def test_post_sends_fields(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="")) as mock_run:
            gh.api("repos/acme/widgets/labels", method="POST", fields={"name": "bug"})
        args = mock_run.call_args[0][0]
        self.assertIn("-f", args)
        self.assertIn("name=bug", args)

    def test_failure_raises_gh_command_error(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 404: Not Found")
        with patch("pipeline.gh.subprocess.run", side_effect=exc):
            with self.assertRaises(gh.GhCommandError):
                gh.api("repos/acme/missing")


class ApiStatusTests(unittest.TestCase):
    def test_ok(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout='{"a": 1}')):
            self.assertEqual(gh.api_status("repos/acme/widgets"), ("ok", {"a": 1}))

    def test_missing_on_404(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 404: Not Found")
        with patch("pipeline.gh.subprocess.run", side_effect=exc):
            self.assertEqual(gh.api_status("repos/acme/missing"), ("missing", None))

    def test_blocked_on_other_error(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 403: Forbidden")
        with patch("pipeline.gh.subprocess.run", side_effect=exc):
            self.assertEqual(gh.api_status("repos/acme/widgets"), ("blocked", None))


class IssueViewEditTests(unittest.TestCase):
    def test_view_requests_only_given_fields(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout='{"labels": []}')) as mock_run:
            result = gh.issue_view("acme/widgets", 42, ["labels", "state"])
        self.assertEqual(result, {"labels": []})
        args = mock_run.call_args[0][0]
        self.assertEqual(args, ["gh", "issue", "view", "42", "--repo", "acme/widgets", "--json", "labels,state"])

    def test_edit_is_noop_with_nothing_to_change(self):
        with patch("pipeline.gh.subprocess.run") as mock_run:
            gh.issue_edit("acme/widgets", 42)
        mock_run.assert_not_called()

    def test_edit_adds_and_removes_labels(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc()) as mock_run:
            gh.issue_edit("acme/widgets", 42, add_labels=["status:ready"], remove_labels=["status:needs-refinement"])
        args = mock_run.call_args[0][0]
        self.assertEqual(
            args,
            ["gh", "issue", "edit", "42", "--repo", "acme/widgets",
             "--add-label", "status:ready", "--remove-label", "status:needs-refinement"],
        )

    def test_edit_failure_raises_gh_command_error(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="label not found")
        with patch("pipeline.gh.subprocess.run", side_effect=exc):
            with self.assertRaises(gh.GhCommandError):
                gh.issue_edit("acme/widgets", 42, add_labels=["bogus"])


class PrViewEditCreateTests(unittest.TestCase):
    def test_view_requests_only_given_fields(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout='{"state": "OPEN"}')) as mock_run:
            result = gh.pr_view("acme/widgets", 7, ["state"])
        self.assertEqual(result, {"state": "OPEN"})
        args = mock_run.call_args[0][0]
        self.assertEqual(args, ["gh", "pr", "view", "7", "--repo", "acme/widgets", "--json", "state"])

    def test_edit_is_noop_with_nothing_to_change(self):
        with patch("pipeline.gh.subprocess.run") as mock_run:
            gh.pr_edit("acme/widgets", 7)
        mock_run.assert_not_called()

    def test_create_returns_url(self):
        url = "https://github.com/acme/widgets/pull/8"
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout=f"{url}\n")) as mock_run:
            result = gh.pr_create("acme/widgets", "feature", "main", "Title", "Body")
        self.assertEqual(result, url)
        args = mock_run.call_args[0][0]
        self.assertEqual(
            args,
            ["gh", "pr", "create", "--repo", "acme/widgets", "--head", "feature", "--base", "main",
             "--title", "Title", "--body", "Body"],
        )


class CommentTests(unittest.TestCase):
    def test_issue_comment(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc()) as mock_run:
            gh.issue_comment("acme/widgets", 42, "hello")
        self.assertEqual(
            mock_run.call_args[0][0],
            ["gh", "issue", "comment", "42", "--repo", "acme/widgets", "--body", "hello"],
        )

    def test_pr_comment(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc()) as mock_run:
            gh.pr_comment("acme/widgets", 7, "hello")
        self.assertEqual(
            mock_run.call_args[0][0],
            ["gh", "pr", "comment", "7", "--repo", "acme/widgets", "--body", "hello"],
        )


class PrDiffNamesTests(unittest.TestCase):
    def test_lists_changed_files(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="a.ts\nb.ts\n")) as mock_run:
            self.assertEqual(gh.pr_diff_names("acme/widgets", 7), ["a.ts", "b.ts"])
        self.assertEqual(
            mock_run.call_args[0][0],
            ["gh", "pr", "diff", "7", "--repo", "acme/widgets", "--name-only"],
        )

    def test_drops_blank_lines(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="a.ts\n\nb.ts\n")):
            self.assertEqual(gh.pr_diff_names("acme/widgets", 7), ["a.ts", "b.ts"])

    def test_no_files_is_an_empty_list(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="")):
            self.assertEqual(gh.pr_diff_names("acme/widgets", 7), [])


class RunUrlTests(unittest.TestCase):
    def test_builds_the_run_url_from_actions_env(self):
        with patch.dict("os.environ", {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_RUN_ID": "123"}):
            self.assertEqual(gh.run_url("acme/widgets"), "https://github.com/acme/widgets/actions/runs/123")


class SecretVerbTests(unittest.TestCase):
    def test_verb(self):
        self.assertEqual(gh.secret_verb("A", None), "set")
        self.assertEqual(gh.secret_verb("A", []), "add")
        self.assertEqual(gh.secret_verb("A", ["A"]), "overwrite")


class ListSecretNamesTests(unittest.TestCase):
    def test_lists_names(self):
        body = json.dumps({"secrets": [{"name": "A"}, {"name": "B"}]})
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout=body)):
            self.assertEqual(gh.list_secret_names("acme/widgets"), ["A", "B"])

    def test_none_when_scope_blind(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 403: Forbidden")
        with patch("pipeline.gh.subprocess.run", side_effect=exc):
            self.assertIsNone(gh.list_secret_names("acme/widgets"))


class DefaultBranchTests(unittest.TestCase):
    def test_reads_default_branch(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout='{"default_branch": "trunk"}')):
            self.assertEqual(gh.default_branch("acme/widgets"), "trunk")

    def test_falls_back_to_main_on_unexpected_shape(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="")):
            self.assertEqual(gh.default_branch("acme/widgets"), "main")


class GetFileTests(unittest.TestCase):
    def test_decodes_content(self):
        import base64
        body = json.dumps({"content": base64.b64encode(b"hello").decode()})
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout=body)):
            self.assertEqual(gh.get_file("acme/widgets", "README.md", "main"), "hello")

    def test_raises_on_missing_content(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="{}")):
            with self.assertRaises(gh.GhCommandError):
                gh.get_file("acme/widgets", "README.md", "main")


class PathExistsTests(unittest.TestCase):
    def test_true_when_ok(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout='{"content": ""}')):
            self.assertTrue(gh.path_exists("acme/widgets", "README.md", "main"))

    def test_false_when_missing(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 404: Not Found")
        with patch("pipeline.gh.subprocess.run", side_effect=exc):
            self.assertFalse(gh.path_exists("acme/widgets", "README.md", "main"))

    def test_raises_when_blocked(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 403: Forbidden")
        with patch("pipeline.gh.subprocess.run", side_effect=exc):
            with self.assertRaises(gh.GhCommandError):
                gh.path_exists("acme/widgets", "README.md", "main")


class EnsureAvailableTests(unittest.TestCase):
    def test_raises_when_gh_missing_from_path(self):
        with patch("pipeline.gh.shutil.which", return_value=None):
            with self.assertRaises(gh.GhNotInstalledError):
                gh.ensure_available()

    def test_checks_auth_status_when_gh_present(self):
        with patch("pipeline.gh.shutil.which", return_value="/usr/bin/gh"), \
             patch("pipeline.gh.subprocess.run", return_value=_proc()) as mock_run:
            gh.ensure_available()
        self.assertEqual(mock_run.call_args[0][0], ["gh", "auth", "status"])


if __name__ == "__main__":
    unittest.main()
