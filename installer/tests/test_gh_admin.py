import json
import subprocess
import unittest
from unittest.mock import patch

from pipeline import gh_transport
from interns_install import gh_admin


def _proc(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["gh"], returncode=returncode, stdout=stdout, stderr=stderr)


class ScopeParseTests(unittest.TestCase):
    def test_parse_scopes(self):
        text = "  - Token scopes: 'gist', 'read:org', 'repo'\n"
        self.assertEqual(gh_admin._parse_scopes(text), {"gist", "read:org", "repo"})

    def test_no_scopes_line(self):
        self.assertEqual(gh_admin._parse_scopes("Logged in to github.com"), set())


class SecretVerbTests(unittest.TestCase):
    def test_verb(self):
        self.assertEqual(gh_admin.secret_verb("A", None), "set")
        self.assertEqual(gh_admin.secret_verb("A", []), "add")
        self.assertEqual(gh_admin.secret_verb("A", ["A"]), "overwrite")


class GetFileTests(unittest.TestCase):
    def test_decodes_content(self):
        import base64
        body = json.dumps({"content": base64.b64encode(b"hello").decode()})
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout=body)):
            self.assertEqual(gh_admin.get_file("acme/widgets", "README.md", "main"), "hello")

    def test_raises_on_missing_content(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout="{}")):
            with self.assertRaises(gh_transport.GhCommandError):
                gh_admin.get_file("acme/widgets", "README.md", "main")


class PathExistsTests(unittest.TestCase):
    def test_true_when_ok(self):
        with patch("pipeline.gh_transport.subprocess.run", return_value=_proc(stdout='{"content": ""}')):
            self.assertTrue(gh_admin.path_exists("acme/widgets", "README.md", "main"))

    def test_false_when_missing(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 404: Not Found")
        with patch("pipeline.gh_transport.subprocess.run", side_effect=exc):
            self.assertFalse(gh_admin.path_exists("acme/widgets", "README.md", "main"))

    def test_raises_when_blocked(self):
        exc = subprocess.CalledProcessError(1, ["gh"], output="", stderr="HTTP 403: Forbidden")
        with patch("pipeline.gh_transport.subprocess.run", side_effect=exc):
            with self.assertRaises(gh_transport.GhCommandError):
                gh_admin.path_exists("acme/widgets", "README.md", "main")


class EnsureAvailableTests(unittest.TestCase):
    def test_raises_when_gh_missing_from_path(self):
        with patch("interns_install.gh_admin.shutil.which", return_value=None):
            with self.assertRaises(gh_transport.GhNotInstalledError):
                gh_admin.ensure_available()

    def test_checks_auth_status_when_gh_present(self):
        with patch("interns_install.gh_admin.shutil.which", return_value="/usr/bin/gh"), \
             patch("pipeline.gh_transport.subprocess.run", return_value=_proc()) as mock_run:
            gh_admin.ensure_available()
        self.assertEqual(mock_run.call_args[0][0], ["gh", "auth", "status"])


class AuthScopesTests(unittest.TestCase):
    def test_reads_scopes_without_raising_on_nonzero_exit(self):
        with patch.object(gh_transport.subprocess, "run",
                                return_value=_proc(stderr="Token scopes: 'repo', 'workflow'")) as run:
            self.assertEqual(gh_admin.auth_scopes(), {"repo", "workflow"})
        self.assertEqual(run.call_args.kwargs["check"], False)


class CurrentRepoTests(unittest.TestCase):
    # `gh repo view --json name,owner` payload as returned by a live repo: no owner type.
    VIEW = json.dumps({"name": "widgets", "owner": {"id": "MDEyOk9yZ2FuaXphdGlvbjE=", "login": "acme"}})

    def _current(self, owner_type, explicit=None):
        with patch.object(gh_transport.subprocess, "run", return_value=_proc(self.VIEW)) as run, \
                patch.object(gh_transport, "api", return_value={"owner": {"login": "acme", "type": owner_type}}) as api:
            repo = gh_admin.current_repo(explicit)
        return repo, run, api

    def test_org_owner_resolved_via_repos_endpoint(self):
        repo, run, api = self._current("Organization")
        self.assertEqual(repo, gh_admin.Repo(owner="acme", name="widgets", is_org=True))
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
        with patch.object(gh_transport, "api", return_value=[{"name": "a.py"}, {"name": "b.py"}]):
            self.assertEqual(gh_admin.list_dir("acme/widgets", "src", "main"), ["a.py", "b.py"])

    def test_raises_when_not_a_directory(self):
        with patch.object(gh_transport, "api", return_value={"content": "..."}):
            with self.assertRaises(gh_transport.GhError):
                gh_admin.list_dir("acme/widgets", "src/main.py", "main")


class BranchHeadShaTests(unittest.TestCase):
    def test_returns_sha(self):
        with patch.object(gh_transport, "api", return_value={"object": {"sha": "abc123"}}):
            self.assertEqual(gh_admin.branch_head_sha("acme/widgets", "main"), "abc123")

    def test_raises_on_non_dict_response(self):
        with patch.object(gh_transport, "api", return_value=None):
            with self.assertRaises(gh_transport.GhError):
                gh_admin.branch_head_sha("acme/widgets", "main")


class RefExistsTests(unittest.TestCase):
    def test_true_when_ok(self):
        with patch.object(gh_transport, "api_status", return_value=("ok", {})):
            self.assertTrue(gh_admin.ref_exists("acme/widgets", "metrics"))

    def test_false_when_missing(self):
        with patch.object(gh_transport, "api_status", return_value=("missing", None)):
            self.assertFalse(gh_admin.ref_exists("acme/widgets", "metrics"))

    def test_raises_when_blocked(self):
        with patch.object(gh_transport, "api_status", return_value=("blocked", None)):
            with self.assertRaises(gh_transport.GhError):
                gh_admin.ref_exists("acme/widgets", "metrics")


class CreateBranchTests(unittest.TestCase):
    def test_posts_ref_and_sha(self):
        with patch.object(gh_transport, "api") as api:
            gh_admin.create_branch("acme/widgets", "feat/x", "abc123")
        api.assert_called_once_with(
            "repos/acme/widgets/git/refs", method="POST",
            fields={"ref": "refs/heads/feat/x", "sha": "abc123"})


class CreateBlobTests(unittest.TestCase):
    def test_returns_sha(self):
        with patch.object(gh_transport, "api", return_value={"sha": "blob-sha"}):
            self.assertEqual(gh_admin.create_blob("acme/widgets", "content"), "blob-sha")

    def test_raises_on_non_dict_response(self):
        with patch.object(gh_transport, "api", return_value=None):
            with self.assertRaises(gh_transport.GhError):
                gh_admin.create_blob("acme/widgets", "content")


class CreateTreeTests(unittest.TestCase):
    def test_returns_sha(self):
        with patch.object(gh_transport, "api", return_value={"sha": "tree-sha"}) as api:
            result = gh_admin.create_tree("acme/widgets", [{"path": "a", "mode": "100644", "type": "blob", "sha": "x"}])
        self.assertEqual(result, "tree-sha")
        kwargs = api.call_args.kwargs
        self.assertEqual(json.loads(kwargs["input_json"])["tree"][0]["path"], "a")

    def test_raises_on_non_dict_response(self):
        with patch.object(gh_transport, "api", return_value=None):
            with self.assertRaises(gh_transport.GhError):
                gh_admin.create_tree("acme/widgets", [])


class CreateCommitTests(unittest.TestCase):
    def test_returns_sha(self):
        with patch.object(gh_transport, "api", return_value={"sha": "commit-sha"}) as api:
            result = gh_admin.create_commit("acme/widgets", "msg", "tree-sha", ["parent-sha"])
        self.assertEqual(result, "commit-sha")
        kwargs = api.call_args.kwargs
        payload = json.loads(kwargs["input_json"])
        self.assertEqual(payload, {"message": "msg", "tree": "tree-sha", "parents": ["parent-sha"]})

    def test_raises_on_non_dict_response(self):
        with patch.object(gh_transport, "api", return_value=None):
            with self.assertRaises(gh_transport.GhError):
                gh_admin.create_commit("acme/widgets", "msg", "tree-sha", [])


class GetExistingFileTests(unittest.TestCase):
    def test_returns_content_and_sha(self):
        import base64
        encoded = base64.b64encode(b"hi").decode()
        with patch.object(gh_transport, "api_status", return_value=("ok", {"content": encoded, "sha": "file-sha"})):
            result = gh_admin.get_existing_file("acme/widgets", "a.txt", "main")
        self.assertEqual(result, ("hi", "file-sha"))

    def test_none_when_missing(self):
        with patch.object(gh_transport, "api_status", return_value=("missing", None)):
            self.assertIsNone(gh_admin.get_existing_file("acme/widgets", "a.txt", "main"))

    def test_raises_when_blocked(self):
        with patch.object(gh_transport, "api_status", return_value=("blocked", None)):
            with self.assertRaises(gh_transport.GhError):
                gh_admin.get_existing_file("acme/widgets", "a.txt", "main")

    def test_raises_when_ok_but_content_missing(self):
        with patch.object(gh_transport, "api_status", return_value=("ok", {"sha": "x"})):
            with self.assertRaises(gh_transport.GhError):
                gh_admin.get_existing_file("acme/widgets", "a.txt", "main")


class PutFileTests(unittest.TestCase):
    def test_create_without_sha(self):
        with patch.object(gh_transport, "api") as api:
            gh_admin.put_file("acme/widgets", "a.txt", "hello", "chore: add a.txt", "main")
        args, kwargs = api.call_args
        self.assertEqual(args[0], "repos/acme/widgets/contents/a.txt")
        self.assertEqual(kwargs["method"], "PUT")
        self.assertNotIn("sha", kwargs["fields"])

    def test_update_includes_sha(self):
        with patch.object(gh_transport, "api") as api:
            gh_admin.put_file("acme/widgets", "a.txt", "hello", "chore: update a.txt", "main", sha="old-sha")
        kwargs = api.call_args.kwargs
        self.assertEqual(kwargs["fields"]["sha"], "old-sha")


class BranchProtectionTests(unittest.TestCase):
    def test_set_puts_the_protection_body(self):
        with patch.object(gh_transport, "api") as api:
            gh_admin.set_branch_protection("o/r", "main", {"allow_deletions": False})
        api.assert_called_once_with("repos/o/r/branches/main/protection", method="PUT",
                                    input_json='{"allow_deletions": false}')


class SetVariableTests(unittest.TestCase):
    def test_tolerates_missing_variable_on_delete(self):
        missing = gh_transport.GhCommandError("`gh variable delete` failed: HTTP 404: Not Found")
        with patch.object(gh_transport, "run", side_effect=[missing, None]) as run:
            gh_admin.set_variable("acme/widgets", "V", "1")
        self.assertEqual(run.call_count, 2)

    def test_raises_on_other_delete_failure(self):
        denied = gh_transport.GhCommandError("`gh variable delete` failed: HTTP 403: Forbidden")
        with patch.object(gh_transport, "run", side_effect=denied) as run:
            with self.assertRaises(gh_transport.GhCommandError):
                gh_admin.set_variable("acme/widgets", "V", "1")
        run.assert_called_once()
