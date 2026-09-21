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

    def test_list_requests_given_fields_and_state(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout='[{"number": 1}]')) as mock_run:
            result = gh.pr_list("acme/widgets", ["number"])
        self.assertEqual(result, [{"number": 1}])
        self.assertEqual(
            mock_run.call_args[0][0],
            ["gh", "pr", "list", "--repo", "acme/widgets", "--state", "open", "--limit", "1000", "--json", "number"],
        )

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


class PrUrlTests(unittest.TestCase):
    def test_builds_the_pr_url_from_actions_env(self):
        with patch.dict("os.environ", {"GITHUB_SERVER_URL": "https://github.com"}):
            self.assertEqual(gh.pr_url("acme/widgets", 12), "https://github.com/acme/widgets/pull/12")

    def test_explicit_server_url_overrides_the_env_and_needs_no_env_var(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                gh.pr_url("acme/widgets", 12, server_url="https://ghe.example.com"),
                "https://ghe.example.com/acme/widgets/pull/12",
            )


class PrChecksTests(unittest.TestCase):
    def test_returns_the_parsed_checks(self):
        checks = [{"name": "test", "bucket": "pass", "link": "https://x"}]
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout=json.dumps(checks))) as mock_run:
            self.assertEqual(gh.pr_checks("acme/widgets", 5), checks)
        self.assertEqual(
            mock_run.call_args[0][0],
            ["gh", "pr", "checks", "5", "--repo", "acme/widgets", "--json", "name,bucket,link"],
        )

    def test_empty_list_on_malformed_output(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="not json")):
            self.assertEqual(gh.pr_checks("acme/widgets", 5), [])

    def test_empty_list_on_a_non_array_body(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout='{"a": 1}')):
            self.assertEqual(gh.pr_checks("acme/widgets", 5), [])


class ApiAllPagesTests(unittest.TestCase):
    def test_flattens_every_page(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout='[[1, 2], [3]]')) as mock_run:
            self.assertEqual(gh.api_all_pages("repos/acme/widgets/pulls/1/reviews"), [1, 2, 3])
        args = mock_run.call_args[0][0]
        self.assertIn("--paginate", args)
        self.assertIn("--slurp", args)


class DispatchWorkflowTests(unittest.TestCase):
    def test_omits_ref_when_none(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc()) as mock_run:
            gh.dispatch_workflow("acme/widgets", "code-pipeline.yml", None, {"phase": "coder"})
        args = mock_run.call_args[0][0]
        self.assertNotIn("--ref", args)
        self.assertEqual(
            args,
            ["gh", "workflow", "run", "code-pipeline.yml", "--repo", "acme/widgets", "-f", "phase=coder"],
        )

    def test_includes_ref_when_given(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc()) as mock_run:
            gh.dispatch_workflow("acme/widgets", "install.yml", "main", {})
        args = mock_run.call_args[0][0]
        self.assertIn("--ref", args)
        self.assertIn("main", args)


class SecretVerbTests(unittest.TestCase):
    def test_verb(self):
        self.assertEqual(gh.secret_verb("A", None), "set")
        self.assertEqual(gh.secret_verb("A", []), "add")
        self.assertEqual(gh.secret_verb("A", ["A"]), "overwrite")


class ListSecretNamesTests(unittest.TestCase):
    def test_lists_names_across_pages(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="A\nB\n")):
            self.assertEqual(gh.list_secret_names("acme/widgets"), ["A", "B"])

    def test_none_when_scope_blind(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 403: Forbidden")
        with patch("pipeline.gh.subprocess.run", side_effect=exc):
            self.assertIsNone(gh.list_secret_names("acme/widgets"))


class ListVariableNamesTests(unittest.TestCase):
    def test_lists_names_across_pages(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="A\nB\n")):
            self.assertEqual(gh.list_variable_names("acme/widgets"), ["A", "B"])

    def test_none_when_scope_blind(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 403: Forbidden")
        with patch("pipeline.gh.subprocess.run", side_effect=exc):
            self.assertIsNone(gh.list_variable_names("acme/widgets"))


class DefaultBranchTests(unittest.TestCase):
    def test_reads_default_branch(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout='{"default_branch": "trunk"}')):
            self.assertEqual(gh.default_branch("acme/widgets"), "trunk")

    def test_raises_on_unexpected_shape(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="")):
            with self.assertRaises(gh.GhCommandError):
                gh.default_branch("acme/widgets")

    def test_raises_when_key_missing(self):
        with patch("pipeline.gh.subprocess.run", return_value=_proc(stdout="{}")):
            with self.assertRaises(gh.GhCommandError):
                gh.default_branch("acme/widgets")


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


class AuthScopesTests(unittest.TestCase):
    def test_reads_scopes_without_raising_on_nonzero_exit(self):
        with patch.object(gh.subprocess, "run",
                                return_value=_proc(stderr="Token scopes: 'repo', 'workflow'")) as run:
            self.assertEqual(gh.auth_scopes(), {"repo", "workflow"})
        self.assertEqual(run.call_args.kwargs["check"], False)


class CurrentRepoTests(unittest.TestCase):
    # `gh repo view --json name,owner` payload as returned by a live repo: no owner type.
    VIEW = json.dumps({"name": "widgets", "owner": {"id": "MDEyOk9yZ2FuaXphdGlvbjE=", "login": "acme"}})

    def _current(self, owner_type, explicit=None):
        with patch.object(gh.subprocess, "run", return_value=_proc(self.VIEW)) as run, \
                patch.object(gh, "api", return_value={"owner": {"login": "acme", "type": owner_type}}) as api:
            repo = gh.current_repo(explicit)
        return repo, run, api

    def test_org_owner_resolved_via_repos_endpoint(self):
        repo, run, api = self._current("Organization")
        self.assertEqual(repo, gh.Repo(owner="acme", name="widgets", is_org=True))
        api.assert_called_once_with("repos/acme/widgets")
        self.assertNotIn("acme/widgets", run.call_args[0][0])

    def test_user_owner_is_not_org(self):
        repo, _, _ = self._current("User")
        self.assertFalse(repo.is_org)

    def test_explicit_repo_is_passed_through(self):
        _, run, _ = self._current("Organization", explicit="acme/widgets")
        self.assertIn("acme/widgets", run.call_args[0][0])


class ListDirTests(unittest.TestCase):
    def test_returns_entry_names(self):
        with patch.object(gh, "api", return_value=[{"name": "a.py"}, {"name": "b.py"}]):
            self.assertEqual(gh.list_dir("acme/widgets", "src", "main"), ["a.py", "b.py"])

    def test_raises_when_not_a_directory(self):
        with patch.object(gh, "api", return_value={"content": "..."}):
            with self.assertRaises(gh.GhError):
                gh.list_dir("acme/widgets", "src/main.py", "main")


class BranchHeadShaTests(unittest.TestCase):
    def test_returns_sha(self):
        with patch.object(gh, "api", return_value={"object": {"sha": "abc123"}}):
            self.assertEqual(gh.branch_head_sha("acme/widgets", "main"), "abc123")

    def test_raises_on_non_dict_response(self):
        with patch.object(gh, "api", return_value=None):
            with self.assertRaises(gh.GhError):
                gh.branch_head_sha("acme/widgets", "main")


class RefExistsTests(unittest.TestCase):
    def test_true_when_ok(self):
        with patch.object(gh, "api_status", return_value=("ok", {})):
            self.assertTrue(gh.ref_exists("acme/widgets", "metrics"))

    def test_false_when_missing(self):
        with patch.object(gh, "api_status", return_value=("missing", None)):
            self.assertFalse(gh.ref_exists("acme/widgets", "metrics"))

    def test_raises_when_blocked(self):
        with patch.object(gh, "api_status", return_value=("blocked", None)):
            with self.assertRaises(gh.GhError):
                gh.ref_exists("acme/widgets", "metrics")


class CreateBranchTests(unittest.TestCase):
    def test_posts_ref_and_sha(self):
        with patch.object(gh, "api") as api:
            gh.create_branch("acme/widgets", "feat/x", "abc123")
        api.assert_called_once_with(
            "repos/acme/widgets/git/refs", method="POST",
            fields={"ref": "refs/heads/feat/x", "sha": "abc123"})


class CreateBlobTests(unittest.TestCase):
    def test_returns_sha(self):
        with patch.object(gh, "api", return_value={"sha": "blob-sha"}):
            self.assertEqual(gh.create_blob("acme/widgets", "content"), "blob-sha")

    def test_raises_on_non_dict_response(self):
        with patch.object(gh, "api", return_value=None):
            with self.assertRaises(gh.GhError):
                gh.create_blob("acme/widgets", "content")


class CreateTreeTests(unittest.TestCase):
    def test_returns_sha(self):
        with patch.object(gh, "api", return_value={"sha": "tree-sha"}) as api:
            result = gh.create_tree("acme/widgets", [{"path": "a", "mode": "100644", "type": "blob", "sha": "x"}])
        self.assertEqual(result, "tree-sha")
        kwargs = api.call_args.kwargs
        self.assertEqual(json.loads(kwargs["input_json"])["tree"][0]["path"], "a")

    def test_raises_on_non_dict_response(self):
        with patch.object(gh, "api", return_value=None):
            with self.assertRaises(gh.GhError):
                gh.create_tree("acme/widgets", [])


class CreateCommitTests(unittest.TestCase):
    def test_returns_sha(self):
        with patch.object(gh, "api", return_value={"sha": "commit-sha"}) as api:
            result = gh.create_commit("acme/widgets", "msg", "tree-sha", ["parent-sha"])
        self.assertEqual(result, "commit-sha")
        kwargs = api.call_args.kwargs
        payload = json.loads(kwargs["input_json"])
        self.assertEqual(payload, {"message": "msg", "tree": "tree-sha", "parents": ["parent-sha"]})

    def test_raises_on_non_dict_response(self):
        with patch.object(gh, "api", return_value=None):
            with self.assertRaises(gh.GhError):
                gh.create_commit("acme/widgets", "msg", "tree-sha", [])


class GetExistingFileTests(unittest.TestCase):
    def test_returns_content_and_sha(self):
        import base64
        encoded = base64.b64encode(b"hi").decode()
        with patch.object(gh, "api_status", return_value=("ok", {"content": encoded, "sha": "file-sha"})):
            result = gh.get_existing_file("acme/widgets", "a.txt", "main")
        self.assertEqual(result, ("hi", "file-sha"))

    def test_none_when_missing(self):
        with patch.object(gh, "api_status", return_value=("missing", None)):
            self.assertIsNone(gh.get_existing_file("acme/widgets", "a.txt", "main"))

    def test_raises_when_blocked(self):
        with patch.object(gh, "api_status", return_value=("blocked", None)):
            with self.assertRaises(gh.GhError):
                gh.get_existing_file("acme/widgets", "a.txt", "main")

    def test_raises_when_ok_but_content_missing(self):
        with patch.object(gh, "api_status", return_value=("ok", {"sha": "x"})):
            with self.assertRaises(gh.GhError):
                gh.get_existing_file("acme/widgets", "a.txt", "main")


class PutFileTests(unittest.TestCase):
    def test_create_without_sha(self):
        with patch.object(gh, "api") as api:
            gh.put_file("acme/widgets", "a.txt", "hello", "chore: add a.txt", "main")
        args, kwargs = api.call_args
        self.assertEqual(args[0], "repos/acme/widgets/contents/a.txt")
        self.assertEqual(kwargs["method"], "PUT")
        self.assertNotIn("sha", kwargs["fields"])

    def test_update_includes_sha(self):
        with patch.object(gh, "api") as api:
            gh.put_file("acme/widgets", "a.txt", "hello", "chore: update a.txt", "main", sha="old-sha")
        kwargs = api.call_args.kwargs
        self.assertEqual(kwargs["fields"]["sha"], "old-sha")


class PrCreateTests(unittest.TestCase):
    def test_returns_pr_url(self):
        with patch.object(gh.subprocess, "run",
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
        with patch.object(gh.subprocess, "run", side_effect=err):
            with self.assertRaises(gh.GhError):
                gh.pr_create("acme/widgets", "feat/x", "main", "Title", "Body")


class SharedClientAdditionsTests(unittest.TestCase):
    def test_error_names_the_subcommand_without_echoing_the_body(self):
        err = subprocess.CalledProcessError(1, ["gh"], stderr="boom")
        with patch.object(gh.subprocess, "run", side_effect=err):
            with self.assertRaises(gh.GhCommandError) as ctx:
                gh.issue_comment("o/r", 5, "SECRET-BODY")
        self.assertIn("issue comment 5", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))
        self.assertNotIn("SECRET-BODY", str(ctx.exception))

    def test_issue_edit_passes_body_and_title(self):
        with patch.object(gh.subprocess, "run", return_value=_proc("url")) as run:
            out = gh.issue_edit("o/r", 5, body="B", title="T")
        self.assertEqual(out, "url")
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("--body") + 1], "B")
        self.assertEqual(cmd[cmd.index("--title") + 1], "T")

    def test_issue_edit_noop_without_changes(self):
        with patch.object(gh.subprocess, "run") as run:
            self.assertEqual(gh.issue_edit("o/r", 5), "")
        run.assert_not_called()

    def test_issue_list_filters_by_label(self):
        with patch.object(gh.subprocess, "run", return_value=_proc('[{"number": 1}]')) as run:
            self.assertEqual(gh.issue_list("o/r", label="bug"), [{"number": 1}])
        cmd = run.call_args[0][0]
        self.assertEqual(cmd[cmd.index("--label") + 1], "bug")

    def test_issue_list_without_label(self):
        with patch.object(gh.subprocess, "run", return_value=_proc("[]")) as run:
            gh.issue_list("o/r")
        self.assertNotIn("--label", run.call_args[0][0])

    def test_graphql_sends_query_and_typed_variables(self):
        with patch.object(gh.subprocess, "run", return_value=_proc('{"data": {}}')) as run:
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
