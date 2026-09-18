import unittest
from unittest import mock

from interns_install import cli, gh
from interns_install.apps import APPS
from interns_install.cli import (
    _collect_missing_files,
    _parse_args,
    _provision_app,
    _secret_verb,
    _stage_install_files,
    _use_existing_app,
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


CODER = next(s for s in APPS if s.key == "coder")


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


def _confirm_sequence(*answers: bool):
    """A con.confirm stand-in that returns each answer in turn, by call order."""
    it = iter(answers)
    return lambda question, default=False: next(it)


class ReuseAppTests(unittest.TestCase):
    def test_flag_writes_variable_and_keeps_existing_key(self):
        con = Console(assume_yes=True)
        with mock.patch.multiple(cli.gh, set_variable=mock.DEFAULT,
                                 set_secret=mock.DEFAULT) as m:
            _use_existing_app(con, _repo(), CODER, "Iv1.aaa", "interns-coder",
                              existing_secrets=[CODER.key_secret])
        m["set_variable"].assert_called_once_with("acme/widgets", CODER.client_id_var, "Iv1.aaa")
        m["set_secret"].assert_not_called()
        self.assertTrue(any("installed on acme/widgets" in n for n in con.manual))

    def test_flag_without_key_records_manual_under_yes(self):
        con = Console(assume_yes=True)
        with mock.patch.multiple(cli.gh, set_variable=mock.DEFAULT,
                                 set_secret=mock.DEFAULT) as m:
            _use_existing_app(con, _repo(), CODER, "Iv1.aaa", "interns-coder",
                              existing_secrets=[])
        m["set_variable"].assert_called_once()
        m["set_secret"].assert_not_called()
        self.assertTrue(any(CODER.key_secret in n for n in con.manual))

    def test_minted_name_is_namespaced_per_owner(self):
        self.assertEqual(CODER.name_for("Acme"), "interns-coder-acme")

    def test_provision_reuses_when_operator_confirms_existing_app(self):
        """No API call decides this -- GitHub can't tell us about a private
        App even for its own owner (confirmed hands-on, see #88 follow-up).
        The operator is asked "already have one?" first (not "set up now?"
        first, which read as "create a new one" and made "no" skip the App
        entirely instead of reaching the reuse question) and, on yes, is
        prompted for the Client ID via _use_existing_app's own fallback."""
        con = Console(assume_yes=False)
        con.confirm = _confirm_sequence(True)  # "already have it?"
        con.prompt = lambda q: "Iv1.existing"
        with mock.patch.object(cli, "ManifestServer") as server, \
             mock.patch.object(cli.webbrowser, "open"), \
             mock.patch.multiple(cli.gh, set_variable=mock.DEFAULT, set_secret=mock.DEFAULT) as m:
            _provision_app(con, _repo(), CODER, None, existing_secrets=[CODER.key_secret])
        server.assert_not_called()
        m["set_variable"].assert_called_once_with("acme/widgets", CODER.client_id_var, "Iv1.existing")

    def test_provision_mints_when_operator_says_no_existing_app(self):
        con = Console(assume_yes=False, dry_run=True)
        con.confirm = _confirm_sequence(False, True)  # "already have it?" then "create new?"
        _provision_app(con, _repo(), CODER, None, existing_secrets=[])
        self.assertTrue(any("via manifest" in p for p in con.planned))

    def test_provision_records_manual_todo_when_operator_declines_both(self):
        con = Console(assume_yes=False, dry_run=True)
        con.confirm = _confirm_sequence(False, False)  # "already have it?" then "create new?"
        _provision_app(con, _repo(), CODER, None, existing_secrets=[])
        self.assertFalse(any("via manifest" in p for p in con.planned))
        self.assertTrue(any(CODER.client_id_var in n for n in con.manual))

    def test_provision_skips_reuse_question_under_yes(self):
        """--yes has no one to ask -- it must fall straight to minting rather
        than silently answering the reuse question for the operator."""
        con = Console(assume_yes=True, dry_run=True)
        with mock.patch.object(cli, "ManifestServer") as server:
            _provision_app(con, _repo(), CODER, None, existing_secrets=[])
        # dry_run short-circuits before ManifestServer is ever constructed;
        # the assertion that matters is the mint path, not this call.
        self.assertTrue(any("via manifest" in p for p in con.planned))


class StageInstallFilesTests(unittest.TestCase):
    def _repo(self):
        return gh.Repo(owner="acme", name="widgets", is_org=False)

    def test_collect_only_missing_files(self):
        present = {".github/workflows/issue-pipeline.yml", ".github/interns.yml", "Makefile"}
        src_for_dest = {dest: src for src, dest in cli.INSTALL_FILES.items()}

        def existing(repo, path, ref):
            return (f"body:{src_for_dest[path]}", "sha-1") if path in present else None

        with mock.patch.object(cli.gh, "path_exists",
                               side_effect=lambda r, p, ref: p in present), \
             mock.patch.object(cli.gh, "get_existing_file", side_effect=existing), \
             mock.patch.object(cli.gh, "get_file", side_effect=lambda r, p, ref: f"body:{p}"):
            wanted = _collect_missing_files(self._repo(), "main", issue_templates=False)

        self.assertEqual(set(wanted), {
            ".github/workflows/install.yml",
            ".github/workflows/code-pipeline.yml",
        })
        self.assertIsNone(wanted[".github/workflows/install.yml"][1])

    def test_collect_flags_drifted_wrapper_file(self):
        """A wrapper file that's present but stale is re-synced, not skipped --
        this is the #88 fix: presence alone used to mean "nothing to do"."""
        src_for_dest = {dest: src for src, dest in cli.INSTALL_FILES.items()}

        def existing(repo, path, ref):
            if path == ".github/workflows/install.yml":
                return ("stale content", "sha-old")
            return (f"body:{src_for_dest[path]}", "sha-1")

        with mock.patch.object(cli.gh, "path_exists", return_value=True), \
             mock.patch.object(cli.gh, "get_existing_file", side_effect=existing), \
             mock.patch.object(cli.gh, "get_file", side_effect=lambda r, p, ref: f"body:{p}"):
            wanted = _collect_missing_files(self._repo(), "main", issue_templates=False)

        self.assertEqual(set(wanted), {".github/workflows/install.yml"})
        content, sha = wanted[".github/workflows/install.yml"]
        self.assertEqual(content, "body:templates/workflows/install.yml")
        self.assertEqual(sha, "sha-old")

    def test_collect_never_overwrites_existing_config_files(self):
        """interns.yml/Makefile carry consumer-local edits -- only added when
        absent, regardless of content drift from the template."""
        with mock.patch.object(cli.gh, "path_exists", return_value=True), \
             mock.patch.object(cli.gh, "get_existing_file",
                               return_value=("body:templates/workflows/install.yml", "sha-1")), \
             mock.patch.object(cli.gh, "get_file", side_effect=lambda r, p, ref: f"body:{p}"):
            wanted = _collect_missing_files(self._repo(), "main", issue_templates=False)

        self.assertNotIn(".github/interns.yml", wanted)
        self.assertNotIn("Makefile", wanted)

    def test_collect_substitutes_ref_placeholder(self):
        tmpl = "uses: abi83/interns/.github/workflows/install.yml@__INTERNS_REF__"
        with mock.patch.object(cli.gh, "path_exists", return_value=False), \
             mock.patch.object(cli.gh, "get_existing_file", return_value=None), \
             mock.patch.object(cli.gh, "get_file", return_value=tmpl), \
             mock.patch.object(cli, "INTERNS_REF", "v9.9.9"):
            wanted = _collect_missing_files(self._repo(), "main", issue_templates=False)

        for content, _sha in wanted.values():
            self.assertNotIn("__INTERNS_REF__", content)
            self.assertIn("@v9.9.9", content)

    def test_collect_pulls_issue_templates_when_dir_absent(self):
        with mock.patch.object(cli.gh, "path_exists", return_value=False), \
             mock.patch.object(cli.gh, "get_existing_file", return_value=None), \
             mock.patch.object(cli.gh, "list_dir", return_value=["bug.md", "config.yml"]), \
             mock.patch.object(cli.gh, "get_file", side_effect=lambda r, p, ref: f"body:{p}"):
            wanted = _collect_missing_files(self._repo(), "main", issue_templates=True)

        self.assertIn(".github/ISSUE_TEMPLATE/bug.md", wanted)
        self.assertIn(".github/ISSUE_TEMPLATE/config.yml", wanted)

    def test_opens_one_pr_for_all_missing_files(self):
        con = Console(assume_yes=True)
        with mock.patch.object(cli, "_collect_missing_files",
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
        with mock.patch.object(cli, "_collect_missing_files",
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
        with mock.patch.object(cli, "_collect_missing_files", return_value={}), \
             mock.patch.object(cli.gh, "create_pr") as create_pr:
            url = _stage_install_files(con, self._repo(), "main", issue_templates=False)
        self.assertIsNone(url)
        create_pr.assert_not_called()

    def test_dry_run_makes_no_calls(self):
        con = Console(assume_yes=True, dry_run=True)
        with mock.patch.object(cli.gh, "get_file") as get_file:
            _stage_install_files(con, self._repo(), "main", issue_templates=False)
        get_file.assert_not_called()
        self.assertTrue(con.manual)


if __name__ == "__main__":
    unittest.main()
