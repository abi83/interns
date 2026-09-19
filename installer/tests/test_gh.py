import json
import subprocess
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


# ---------------------------------------------------------------------------
# _run — the subprocess boundary every other function in this module goes
# through, so its failure modes are tested once here rather than re-derived
# per caller.
# ---------------------------------------------------------------------------


def _proc(stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["gh"], returncode=0, stdout=stdout, stderr=stderr)


class RunTests(unittest.TestCase):
    def test_prefixes_gh_and_returns_completed_process(self):
        with mock.patch.object(gh.subprocess, "run", return_value=_proc("ok")) as run:
            result = gh._run(["repo", "view"])
        run.assert_called_once_with(
            ["gh", "repo", "view"], input=None, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, "ok")

    def test_missing_gh_binary_raises_gh_error(self):
        with mock.patch.object(gh.subprocess, "run", side_effect=FileNotFoundError()):
            with self.assertRaises(gh.GhError):
                gh._run(["repo", "view"])

    def test_nonzero_exit_raises_gh_error_with_stderr(self):
        err = subprocess.CalledProcessError(1, ["gh", "repo", "view"], output="", stderr="not found")
        with mock.patch.object(gh.subprocess, "run", side_effect=err):
            with self.assertRaises(gh.GhError) as ctx:
                gh._run(["repo", "view"])
        self.assertIn("not found", str(ctx.exception))

    def test_check_false_is_not_swallowed_by_boundary(self):
        with mock.patch.object(gh.subprocess, "run", return_value=_proc()) as run:
            gh._run(["auth", "status"], check=False)
        self.assertEqual(run.call_args.kwargs["check"], False)


class EnsureAvailableTests(unittest.TestCase):
    def test_raises_when_gh_not_on_path(self):
        with mock.patch.object(gh.shutil, "which", return_value=None):
            with self.assertRaises(gh.GhError):
                gh.ensure_available()

    def test_passes_when_gh_present_and_authenticated(self):
        with mock.patch.object(gh.shutil, "which", return_value="/usr/bin/gh"), \
             mock.patch.object(gh.subprocess, "run", return_value=_proc()) as run:
            gh.ensure_available()
        self.assertEqual(run.call_args[0][0], ["gh", "auth", "status"])

    def test_raises_when_gh_present_but_not_authenticated(self):
        err = subprocess.CalledProcessError(1, ["gh", "auth", "status"], output="", stderr="not logged in")
        with mock.patch.object(gh.shutil, "which", return_value="/usr/bin/gh"), \
             mock.patch.object(gh.subprocess, "run", side_effect=err):
            with self.assertRaises(gh.GhError):
                gh.ensure_available()


class AuthScopesTests(unittest.TestCase):
    def test_reads_scopes_without_raising_on_nonzero_exit(self):
        with mock.patch.object(gh.subprocess, "run",
                                return_value=_proc(stderr="Token scopes: 'repo', 'workflow'")) as run:
            self.assertEqual(gh.auth_scopes(), {"repo", "workflow"})
        self.assertEqual(run.call_args.kwargs["check"], False)


class ApiTests(unittest.TestCase):
    def test_get_parses_json_body(self):
        with mock.patch.object(gh.subprocess, "run", return_value=_proc(json.dumps({"a": 1}))) as run:
            result = gh.api("repos/acme/widgets")
        self.assertEqual(result, {"a": 1})
        cmd = run.call_args[0][0]
        self.assertIn("repos/acme/widgets", cmd)
        self.assertIn("-X", cmd)
        self.assertIn("GET", cmd)

    def test_empty_stdout_returns_none(self):
        with mock.patch.object(gh.subprocess, "run", return_value=_proc("")):
            self.assertIsNone(gh.api("repos/acme/widgets"))

    def test_fields_are_passed_as_dash_f(self):
        with mock.patch.object(gh.subprocess, "run", return_value=_proc("")) as run:
            gh.api("repos/acme/widgets", method="POST", fields={"ref": "refs/heads/x", "sha": "abc"})
        cmd = run.call_args[0][0]
        self.assertIn("-f", cmd)
        self.assertIn("ref=refs/heads/x", cmd)
        self.assertIn("sha=abc", cmd)

    def test_input_json_is_sent_over_stdin(self):
        with mock.patch.object(gh.subprocess, "run", return_value=_proc("")) as run:
            gh.api("repos/acme/widgets/git/trees", method="POST", input_json='{"tree": []}')
        cmd = run.call_args[0][0]
        self.assertIn("--input", cmd)
        self.assertIn("-", cmd)
        self.assertEqual(run.call_args.kwargs["input"], '{"tree": []}')

    def test_nonzero_exit_propagates_as_gh_error(self):
        err = subprocess.CalledProcessError(1, ["gh", "api"], output="", stderr='{"message":"Not Found"}')
        with mock.patch.object(gh.subprocess, "run", side_effect=err):
            with self.assertRaises(gh.GhError):
                gh.api("repos/acme/widgets/nope")


class ApiStatusTests(unittest.TestCase):
    def test_ok(self):
        with mock.patch.object(gh, "api", return_value={"a": 1}):
            self.assertEqual(gh.api_status("repos/acme/widgets"), ("ok", {"a": 1}))

    def test_404_is_missing(self):
        with mock.patch.object(gh, "api", side_effect=gh.GhError("gh api repos/x failed: HTTP 404: Not Found")):
            self.assertEqual(gh.api_status("repos/acme/widgets"), ("missing", None))

    def test_403_is_blocked(self):
        with mock.patch.object(gh, "api", side_effect=gh.GhError("gh api repos/x failed: HTTP 403: Forbidden")):
            self.assertEqual(gh.api_status("repos/acme/widgets"), ("blocked", None))

    def test_other_error_is_blocked(self):
        with mock.patch.object(gh, "api", side_effect=gh.GhError("gh api repos/x failed: connection reset")):
            self.assertEqual(gh.api_status("repos/acme/widgets"), ("blocked", None))


class CurrentRepoTests(unittest.TestCase):
    def test_parses_owner_and_org_type(self):
        body = json.dumps({"name": "widgets", "owner": {"login": "acme", "type": "Organization"}})
        with mock.patch.object(gh.subprocess, "run", return_value=_proc(body)) as run:
            repo = gh.current_repo(None)
        self.assertEqual(repo, gh.Repo(owner="acme", name="widgets", is_org=True))
        cmd = run.call_args[0][0]
        self.assertNotIn("acme/widgets", cmd)

    def test_user_owner_is_not_org(self):
        body = json.dumps({"name": "widgets", "owner": {"login": "vlkromm", "type": "User"}})
        with mock.patch.object(gh.subprocess, "run", return_value=_proc(body)):
            repo = gh.current_repo(None)
        self.assertFalse(repo.is_org)

    def test_explicit_repo_is_passed_through(self):
        body = json.dumps({"name": "widgets", "owner": {"login": "acme", "type": "Organization"}})
        with mock.patch.object(gh.subprocess, "run", return_value=_proc(body)) as run:
            gh.current_repo("acme/widgets")
        cmd = run.call_args[0][0]
        self.assertIn("acme/widgets", cmd)


class ListSecretNamesTests(unittest.TestCase):
    def test_returns_names(self):
        with mock.patch.object(gh, "api", return_value={"secrets": [{"name": "A"}, {"name": "B"}]}):
            self.assertEqual(gh.list_secret_names("acme/widgets"), ["A", "B"])

    def test_none_on_scope_blind_token(self):
        with mock.patch.object(gh, "api", side_effect=gh.GhError("forbidden")):
            self.assertIsNone(gh.list_secret_names("acme/widgets"))


class ConvertManifestTests(unittest.TestCase):
    def test_returns_conversion_body(self):
        with mock.patch.object(gh, "api", return_value={"pem": "----KEY----", "id": 1}) as api:
            data = gh.convert_manifest("abc123")
        self.assertEqual(data["pem"], "----KEY----")
        args, kwargs = api.call_args
        self.assertIn("app-manifests/abc123/conversions", args[0])
        self.assertEqual(kwargs["method"], "POST")

    def test_raises_when_pem_missing(self):
        with mock.patch.object(gh, "api", return_value={"id": 1}):
            with self.assertRaises(gh.GhError):
                gh.convert_manifest("abc123")

    def test_raises_on_non_dict_response(self):
        with mock.patch.object(gh, "api", return_value=None):
            with self.assertRaises(gh.GhError):
                gh.convert_manifest("abc123")


class GetFileTests(unittest.TestCase):
    def test_decodes_base64_content(self):
        import base64
        encoded = base64.b64encode(b"hello world").decode()
        with mock.patch.object(gh, "api", return_value={"content": encoded}):
            self.assertEqual(gh.get_file("acme/widgets", "README.md", "main"), "hello world")

    def test_raises_when_content_missing(self):
        with mock.patch.object(gh, "api", return_value={}):
            with self.assertRaises(gh.GhError):
                gh.get_file("acme/widgets", "README.md", "main")

    def test_raises_on_non_dict_response(self):
        with mock.patch.object(gh, "api", return_value=[]):
            with self.assertRaises(gh.GhError):
                gh.get_file("acme/widgets", "README.md", "main")


class PathExistsTests(unittest.TestCase):
    def test_true_when_ok(self):
        with mock.patch.object(gh, "api_status", return_value=("ok", {})):
            self.assertTrue(gh.path_exists("acme/widgets", "docs", "main"))

    def test_false_when_missing(self):
        with mock.patch.object(gh, "api_status", return_value=("missing", None)):
            self.assertFalse(gh.path_exists("acme/widgets", "docs", "main"))

    def test_raises_when_blocked(self):
        with mock.patch.object(gh, "api_status", return_value=("blocked", None)):
            with self.assertRaises(gh.GhError):
                gh.path_exists("acme/widgets", "docs", "main")


class ListDirTests(unittest.TestCase):
    def test_returns_entry_names(self):
        with mock.patch.object(gh, "api", return_value=[{"name": "a.py"}, {"name": "b.py"}]):
            self.assertEqual(gh.list_dir("acme/widgets", "src", "main"), ["a.py", "b.py"])

    def test_raises_when_not_a_directory(self):
        with mock.patch.object(gh, "api", return_value={"content": "..."}):
            with self.assertRaises(gh.GhError):
                gh.list_dir("acme/widgets", "src/main.py", "main")


class BranchHeadShaTests(unittest.TestCase):
    def test_returns_sha(self):
        with mock.patch.object(gh, "api", return_value={"object": {"sha": "abc123"}}):
            self.assertEqual(gh.branch_head_sha("acme/widgets", "main"), "abc123")

    def test_raises_on_non_dict_response(self):
        with mock.patch.object(gh, "api", return_value=None):
            with self.assertRaises(gh.GhError):
                gh.branch_head_sha("acme/widgets", "main")


class RefExistsTests(unittest.TestCase):
    def test_true_when_ok(self):
        with mock.patch.object(gh, "api_status", return_value=("ok", {})):
            self.assertTrue(gh.ref_exists("acme/widgets", "metrics"))

    def test_false_when_missing(self):
        with mock.patch.object(gh, "api_status", return_value=("missing", None)):
            self.assertFalse(gh.ref_exists("acme/widgets", "metrics"))

    def test_raises_when_blocked(self):
        with mock.patch.object(gh, "api_status", return_value=("blocked", None)):
            with self.assertRaises(gh.GhError):
                gh.ref_exists("acme/widgets", "metrics")


class CreateBranchTests(unittest.TestCase):
    def test_posts_ref_and_sha(self):
        with mock.patch.object(gh, "api") as api:
            gh.create_branch("acme/widgets", "feat/x", "abc123")
        api.assert_called_once_with(
            "repos/acme/widgets/git/refs", method="POST",
            fields={"ref": "refs/heads/feat/x", "sha": "abc123"})


class CreateBlobTests(unittest.TestCase):
    def test_returns_sha(self):
        with mock.patch.object(gh, "api", return_value={"sha": "blob-sha"}):
            self.assertEqual(gh.create_blob("acme/widgets", "content"), "blob-sha")

    def test_raises_on_non_dict_response(self):
        with mock.patch.object(gh, "api", return_value=None):
            with self.assertRaises(gh.GhError):
                gh.create_blob("acme/widgets", "content")


class CreateTreeTests(unittest.TestCase):
    def test_returns_sha(self):
        with mock.patch.object(gh, "api", return_value={"sha": "tree-sha"}) as api:
            result = gh.create_tree("acme/widgets", [{"path": "a", "mode": "100644", "type": "blob", "sha": "x"}])
        self.assertEqual(result, "tree-sha")
        kwargs = api.call_args.kwargs
        self.assertEqual(json.loads(kwargs["input_json"])["tree"][0]["path"], "a")

    def test_raises_on_non_dict_response(self):
        with mock.patch.object(gh, "api", return_value=None):
            with self.assertRaises(gh.GhError):
                gh.create_tree("acme/widgets", [])


class CreateCommitTests(unittest.TestCase):
    def test_returns_sha(self):
        with mock.patch.object(gh, "api", return_value={"sha": "commit-sha"}) as api:
            result = gh.create_commit("acme/widgets", "msg", "tree-sha", ["parent-sha"])
        self.assertEqual(result, "commit-sha")
        kwargs = api.call_args.kwargs
        payload = json.loads(kwargs["input_json"])
        self.assertEqual(payload, {"message": "msg", "tree": "tree-sha", "parents": ["parent-sha"]})

    def test_raises_on_non_dict_response(self):
        with mock.patch.object(gh, "api", return_value=None):
            with self.assertRaises(gh.GhError):
                gh.create_commit("acme/widgets", "msg", "tree-sha", [])


class GetExistingFileTests(unittest.TestCase):
    def test_returns_content_and_sha(self):
        import base64
        encoded = base64.b64encode(b"hi").decode()
        with mock.patch.object(gh, "api_status", return_value=("ok", {"content": encoded, "sha": "file-sha"})):
            result = gh.get_existing_file("acme/widgets", "a.txt", "main")
        self.assertEqual(result, ("hi", "file-sha"))

    def test_none_when_missing(self):
        with mock.patch.object(gh, "api_status", return_value=("missing", None)):
            self.assertIsNone(gh.get_existing_file("acme/widgets", "a.txt", "main"))

    def test_raises_when_blocked(self):
        with mock.patch.object(gh, "api_status", return_value=("blocked", None)):
            with self.assertRaises(gh.GhError):
                gh.get_existing_file("acme/widgets", "a.txt", "main")

    def test_raises_when_ok_but_content_missing(self):
        with mock.patch.object(gh, "api_status", return_value=("ok", {"sha": "x"})):
            with self.assertRaises(gh.GhError):
                gh.get_existing_file("acme/widgets", "a.txt", "main")


class PutFileTests(unittest.TestCase):
    def test_create_without_sha(self):
        with mock.patch.object(gh, "api") as api:
            gh.put_file("acme/widgets", "a.txt", "hello", "chore: add a.txt", "main")
        args, kwargs = api.call_args
        self.assertEqual(args[0], "repos/acme/widgets/contents/a.txt")
        self.assertEqual(kwargs["method"], "PUT")
        self.assertNotIn("sha", kwargs["fields"])

    def test_update_includes_sha(self):
        with mock.patch.object(gh, "api") as api:
            gh.put_file("acme/widgets", "a.txt", "hello", "chore: update a.txt", "main", sha="old-sha")
        kwargs = api.call_args.kwargs
        self.assertEqual(kwargs["fields"]["sha"], "old-sha")


class CreatePrTests(unittest.TestCase):
    def test_returns_pr_url(self):
        with mock.patch.object(gh.subprocess, "run",
                                return_value=_proc("https://github.com/acme/widgets/pull/9\n")) as run:
            url = gh.create_pr("acme/widgets", "feat/x", "main", "Title", "Body")
        self.assertEqual(url, "https://github.com/acme/widgets/pull/9")
        cmd = run.call_args[0][0]
        self.assertIn("--head", cmd)
        self.assertIn("feat/x", cmd)
        self.assertIn("--base", cmd)
        self.assertIn("main", cmd)

    def test_nonzero_exit_raises_gh_error(self):
        err = subprocess.CalledProcessError(1, ["gh", "pr", "create"], output="", stderr="no commits between main and feat/x")
        with mock.patch.object(gh.subprocess, "run", side_effect=err):
            with self.assertRaises(gh.GhError):
                gh.create_pr("acme/widgets", "feat/x", "main", "Title", "Body")


class DispatchWorkflowTests(unittest.TestCase):
    def test_passes_inputs_as_dash_f(self):
        with mock.patch.object(gh.subprocess, "run", return_value=_proc()) as run:
            gh.dispatch_workflow("acme/widgets", "install.yml", "main", {"foo": "bar"})
        cmd = run.call_args[0][0]
        self.assertIn("install.yml", cmd)
        self.assertIn("--ref", cmd)
        self.assertIn("main", cmd)
        self.assertIn("-f", cmd)
        self.assertIn("foo=bar", cmd)

    def test_nonzero_exit_raises_gh_error(self):
        err = subprocess.CalledProcessError(1, ["gh", "workflow", "run"], output="", stderr="workflow not found")
        with mock.patch.object(gh.subprocess, "run", side_effect=err):
            with self.assertRaises(gh.GhError):
                gh.dispatch_workflow("acme/widgets", "install.yml", "main", {})


if __name__ == "__main__":
    unittest.main()
