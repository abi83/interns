import json
import subprocess
import unittest
from unittest.mock import patch

from pipeline import gh, gh_transport


def _proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr)


class RunTests(unittest.TestCase):
    def test_gh_not_installed(self):
        with patch("pipeline.gh_transport.subprocess.run", side_effect=FileNotFoundError()):
            with self.assertRaises(gh.GhNotInstalledError):
                gh.run(["auth", "status"])

    def test_command_failure_raises_with_stderr(self):
        exc = subprocess.CalledProcessError(1, ["gh", "issue", "view", "1"], output="", stderr="not found")
        with patch("pipeline.gh_transport.subprocess.run", side_effect=exc):
            with self.assertRaisesRegex(gh.GhCommandError, "not found"):
                gh.run(["issue", "view", "1"])

    def test_success_returns_completed_process(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="ok")) as mock_run:
            result = gh.run(["auth", "status"])
        self.assertEqual(result.stdout, "ok")
        self.assertEqual(mock_run.call_args[0][0], ["gh", "auth", "status"])


class ApiTests(unittest.TestCase):
    def test_get_parses_json_body(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout='{"a": 1}')) as mock_run:
            result = gh.api("repos/acme/widgets")
        self.assertEqual(result, {"a": 1})
        args = mock_run.call_args[0][0]
        self.assertIn("repos/acme/widgets", args)
        self.assertIn("GET", args)

    def test_empty_body_returns_none(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="")):
            self.assertIsNone(gh.api("repos/acme/widgets"))

    def test_post_sends_fields(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="")) as mock_run:
            gh.api("repos/acme/widgets/labels", method="POST", fields={"name": "bug"})
        args = mock_run.call_args[0][0]
        self.assertIn("-f", args)
        self.assertIn("name=bug", args)

    def test_failure_raises_gh_command_error(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 404: Not Found")
        with patch("pipeline.gh_transport.subprocess.run", side_effect=exc):
            with self.assertRaises(gh.GhCommandError):
                gh.api("repos/acme/missing")


class ApiStatusTests(unittest.TestCase):
    def test_ok(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout='{"a": 1}')):
            self.assertEqual(gh.api_status("repos/acme/widgets"), ("ok", {"a": 1}))

    def test_missing_on_404(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 404: Not Found")
        with patch("pipeline.gh_transport.subprocess.run", side_effect=exc):
            self.assertEqual(gh.api_status("repos/acme/missing"), ("missing", None))

    def test_blocked_on_403(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 403: Forbidden")
        with patch("pipeline.gh_transport.subprocess.run", side_effect=exc):
            self.assertEqual(gh.api_status("repos/acme/widgets"), ("blocked", None))

    def test_other_errors_raise(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="dial tcp: connection refused")
        with patch("pipeline.gh_transport.subprocess.run", side_effect=exc):
            with self.assertRaises(gh.GhCommandError):
                gh.api_status("repos/acme/widgets")


class IssueViewEditTests(unittest.TestCase):
    def test_view_requests_only_given_fields(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout='{"labels": []}')) as mock_run:
            result = gh.issue_view("acme/widgets", 42, ["labels", "state"])
        self.assertEqual(result, {"labels": []})
        args = mock_run.call_args[0][0]
        self.assertEqual(args, ["gh", "issue", "view", "42", "--repo", "acme/widgets", "--json", "labels,state"])

    def test_edit_is_noop_with_nothing_to_change(self):
        with patch("pipeline.gh_transport.subprocess.run") as mock_run:
            gh.issue_edit("acme/widgets", 42)
        mock_run.assert_not_called()

    def test_edit_adds_and_removes_labels(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc()) as mock_run:
            gh.issue_edit("acme/widgets", 42, add_labels=["status:ready"], remove_labels=["status:needs-refinement"])
        args = mock_run.call_args[0][0]
        self.assertEqual(
            args,
            ["gh", "issue", "edit", "42", "--repo", "acme/widgets",
             "--add-label", "status:ready", "--remove-label", "status:needs-refinement"],
        )

    def test_edit_failure_raises_gh_command_error(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="label not found")
        with patch("pipeline.gh_transport.subprocess.run", side_effect=exc):
            with self.assertRaises(gh.GhCommandError):
                gh.issue_edit("acme/widgets", 42, add_labels=["bogus"])


class PrViewEditCreateTests(unittest.TestCase):
    def test_view_requests_only_given_fields(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout='{"state": "OPEN"}')) as mock_run:
            result = gh.pr_view("acme/widgets", 7, ["state"])
        self.assertEqual(result, {"state": "OPEN"})
        args = mock_run.call_args[0][0]
        self.assertEqual(args, ["gh", "pr", "view", "7", "--repo", "acme/widgets", "--json", "state"])

    def test_list_requests_given_fields_and_state(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout='[{"number": 1}]')) as mock_run:
            result = gh.pr_list("acme/widgets", ["number"])
        self.assertEqual(result, [{"number": 1}])
        self.assertEqual(
            mock_run.call_args[0][0],
            ["gh", "pr", "list", "--repo", "acme/widgets", "--state", "open", "--limit", "1000", "--json", "number"],
        )

    def test_list_raises_when_truncated(self):
        prs = json.dumps([{"number": n} for n in range(1000)])
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout=prs)):
            with self.assertRaises(gh.GhError):
                gh.pr_list("acme/widgets", ["number"])

    def test_edit_is_noop_with_nothing_to_change(self):
        with patch("pipeline.gh_transport.subprocess.run") as mock_run:
            gh.pr_edit("acme/widgets", 7)
        mock_run.assert_not_called()

    def test_create_returns_url(self):
        url = "https://github.com/acme/widgets/pull/8"
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout=f"{url}\n")) as mock_run:
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
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc()) as mock_run:
            gh.issue_comment("acme/widgets", 42, "hello")
        self.assertEqual(
            mock_run.call_args[0][0],
            ["gh", "issue", "comment", "42", "--repo", "acme/widgets", "--body", "hello"],
        )

    def test_pr_comment(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc()) as mock_run:
            gh.pr_comment("acme/widgets", 7, "hello")
        self.assertEqual(
            mock_run.call_args[0][0],
            ["gh", "pr", "comment", "7", "--repo", "acme/widgets", "--body", "hello"],
        )


class PrDiffNamesTests(unittest.TestCase):
    def test_lists_changed_files(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="a.ts\nb.ts\n")) as mock_run:
            self.assertEqual(gh.pr_diff_names("acme/widgets", 7), ["a.ts", "b.ts"])
        self.assertEqual(
            mock_run.call_args[0][0],
            ["gh", "pr", "diff", "7", "--repo", "acme/widgets", "--name-only"],
        )

    def test_drops_blank_lines(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="a.ts\n\nb.ts\n")):
            self.assertEqual(gh.pr_diff_names("acme/widgets", 7), ["a.ts", "b.ts"])

    def test_no_files_is_an_empty_list(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="")):
            self.assertEqual(gh.pr_diff_names("acme/widgets", 7), [])


class PrChecksTests(unittest.TestCase):
    def test_returns_the_parsed_checks(self):
        checks = [{"name": "test", "bucket": "pass", "link": "https://x"}]
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout=json.dumps(checks))) as mock_run:
            self.assertEqual(gh.pr_checks("acme/widgets", 5), checks)
        self.assertEqual(
            mock_run.call_args[0][0],
            ["gh", "pr", "checks", "5", "--repo", "acme/widgets", "--json", "name,bucket,link"],
        )

    def test_returns_checks_despite_nonzero_exit(self):
        checks = [{"name": "test", "bucket": "fail", "link": "https://x"}]
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout=json.dumps(checks), returncode=1)):
            self.assertEqual(gh.pr_checks("acme/widgets", 5), checks)

    def test_empty_list_when_no_checks_reported(self):
        proc = _proc(stdout="", returncode=1, stderr="no checks reported on the 'x' branch")
        with patch("pipeline.gh_transport.subprocess.run", return_value=proc):
            self.assertEqual(gh.pr_checks("acme/widgets", 5), [])

    def test_raises_on_other_failure(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="", returncode=1, stderr="HTTP 502")):
            with self.assertRaises(gh.GhCommandError):
                gh.pr_checks("acme/widgets", 5)

    def test_raises_on_malformed_output(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="not json")):
            with self.assertRaises(gh.GhCommandError):
                gh.pr_checks("acme/widgets", 5)

    def test_raises_on_a_non_array_body(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout='{"a": 1}')):
            with self.assertRaises(gh.GhCommandError):
                gh.pr_checks("acme/widgets", 5)


class ApiAllPagesTests(unittest.TestCase):
    def test_flattens_every_page(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout='[[1, 2], [3]]')) as mock_run:
            self.assertEqual(gh.api_all_pages("repos/acme/widgets/pulls/1/reviews"), [1, 2, 3])
        args = mock_run.call_args[0][0]
        self.assertIn("--paginate", args)
        self.assertIn("--slurp", args)


class DispatchWorkflowTests(unittest.TestCase):
    def test_omits_ref_when_none(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc()) as mock_run:
            gh.dispatch_workflow("acme/widgets", "code-pipeline.yml", None, {"phase": "coder"})
        args = mock_run.call_args[0][0]
        self.assertNotIn("--ref", args)
        self.assertEqual(
            args,
            ["gh", "workflow", "run", "code-pipeline.yml", "--repo", "acme/widgets", "-f", "phase=coder"],
        )

    def test_includes_ref_when_given(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc()) as mock_run:
            gh.dispatch_workflow("acme/widgets", "install.yml", "main", {})
        args = mock_run.call_args[0][0]
        self.assertIn("--ref", args)
        self.assertIn("main", args)


class ListSecretNamesTests(unittest.TestCase):
    def test_lists_names_across_pages(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="A\nB\n")):
            self.assertEqual(gh.list_secret_names("acme/widgets"), ["A", "B"])

    def test_raises_when_scope_blind(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 403: Forbidden")
        with patch("pipeline.gh_transport.subprocess.run", side_effect=exc):
            with self.assertRaises(gh.GhCommandError):
                gh.list_secret_names("acme/widgets")


class ListVariableNamesTests(unittest.TestCase):
    def test_lists_names_across_pages(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="A\nB\n")):
            self.assertEqual(gh.list_variable_names("acme/widgets"), ["A", "B"])

    def test_raises_when_scope_blind(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 403: Forbidden")
        with patch("pipeline.gh_transport.subprocess.run", side_effect=exc):
            with self.assertRaises(gh.GhCommandError):
                gh.list_variable_names("acme/widgets")


class DefaultBranchTests(unittest.TestCase):
    def test_reads_default_branch(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout='{"default_branch": "trunk"}')):
            self.assertEqual(gh.default_branch("acme/widgets"), "trunk")

    def test_raises_on_unexpected_shape(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="")):
            with self.assertRaises(gh.GhCommandError):
                gh.default_branch("acme/widgets")

    def test_raises_when_key_missing(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="{}")):
            with self.assertRaises(gh.GhCommandError):
                gh.default_branch("acme/widgets")


class PrCreateTests(unittest.TestCase):
    def test_returns_pr_url(self):
        with patch.object(gh_transport.subprocess, "run",
                                return_value=_proc("https://github.com/acme/widgets/pull/9\n")) as run:
            url = gh.pr_create("acme/widgets", "feat/x", "main", "Title", "Body")
        self.assertEqual(url, "https://github.com/acme/widgets/pull/9")
        cmd = run.call_args[0][0]
        self.assertIn("--head", cmd)
        self.assertIn("feat/x", cmd)
        self.assertIn("--base", cmd)
        self.assertIn("main", cmd)

    def test_nonzero_exit_raises_gh_error(self):
        err = subprocess.CalledProcessError(1, ["gh", "pr", "create"], output="", stderr="no commits between main and feat/x")
        with patch.object(gh_transport.subprocess, "run", side_effect=err):
            with self.assertRaises(gh.GhError):
                gh.pr_create("acme/widgets", "feat/x", "main", "Title", "Body")


class SharedClientAdditionsTests(unittest.TestCase):
    def test_error_names_the_subcommand_without_echoing_the_body(self):
        err = subprocess.CalledProcessError(1, ["gh"], stderr="boom")
        with patch.object(gh_transport.subprocess, "run", side_effect=err):
            with self.assertRaises(gh.GhCommandError) as ctx:
                gh.issue_comment("o/r", 5, "SECRET-BODY")
        self.assertIn("issue comment 5", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))
        self.assertNotIn("SECRET-BODY", str(ctx.exception))

    def test_issue_edit_passes_body_and_title(self):
        with patch.object(gh_transport.subprocess, "run", return_value=_proc("url")) as run:
            out = gh.issue_edit("o/r", 5, body="B", title="T")
        self.assertEqual(out, "url")
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("--body") + 1], "B")
        self.assertEqual(cmd[cmd.index("--title") + 1], "T")

    def test_issue_edit_noop_without_changes(self):
        with patch.object(gh_transport.subprocess, "run") as run:
            self.assertEqual(gh.issue_edit("o/r", 5), "")
        run.assert_not_called()

    def test_issue_list_paginates_filters_label_and_drops_prs(self):
        pages = json.dumps([
            [{"number": 1, "title": "a", "labels": [], "state": "open"},
             {"number": 2, "title": "pr", "labels": [], "state": "open", "pull_request": {}}],
            [{"number": 3, "title": "c", "labels": [], "state": "open"}],
        ])
        with patch.object(gh_transport.subprocess, "run", return_value=_proc(pages)) as run:
            result = gh.issue_list("o/r", label="type:bug")
        self.assertEqual([i["number"] for i in result], [1, 3])
        self.assertEqual(result[0]["state"], "OPEN")
        cmd = run.call_args[0][0]
        self.assertIn("--paginate", cmd)
        self.assertIn("repos/o/r/issues?state=open&per_page=100&labels=type%3Abug", cmd)

    def test_label_list_paginates(self):
        pages = json.dumps([[{"name": "a", "color": "fff", "description": "", "id": 1}], [{"name": "b", "color": "000", "description": "d"}]])
        with patch.object(gh_transport.subprocess, "run", return_value=_proc(pages)) as run:
            result = gh.label_list("o/r")
        self.assertEqual([l["name"] for l in result], ["a", "b"])
        self.assertNotIn("id", result[0])
        self.assertIn("--paginate", run.call_args[0][0])

    def test_graphql_sends_query_and_typed_variables(self):
        with patch.object(gh_transport.subprocess, "run", return_value=_proc('{"data": {}}')) as run:
            self.assertEqual(gh.graphql("query {}", owner="o", number=3), {"data": {}})
        cmd = run.call_args[0][0]
        self.assertIn("query=query {}", cmd)
        self.assertIn("owner=o", cmd)
        self.assertIn("number=3", cmd)

    def test_label_names(self):
        with patch.object(gh, "label_list", return_value=[{"name": "bug"}, {"name": "x"}]):
            self.assertEqual(gh.label_names("o/r"), ["bug", "x"])


if __name__ == "__main__":
    unittest.main()
