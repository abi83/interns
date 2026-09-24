import unittest
from unittest import mock

from interns import gh
from interns_install import gh_admin, apps
from interns_install.apps import (
    APP_PERMISSIONS,
    APPS,
    build_manifest,
    convert_manifest,
    provision_app,
    settings_new_url,
    use_existing_app,
)
from interns_install.console import Console


class ConvertManifestTests(unittest.TestCase):
    def test_returns_conversion_body(self):
        with mock.patch.object(gh, "api", return_value={"pem": "----KEY----", "id": 1}) as api:
            data = convert_manifest("abc123")
        self.assertEqual(data["pem"], "----KEY----")
        args, kwargs = api.call_args
        self.assertIn("app-manifests/abc123/conversions", args[0])
        self.assertEqual(kwargs["method"], "POST")

    def test_raises_when_pem_missing(self):
        with mock.patch.object(gh, "api", return_value={"id": 1}):
            with self.assertRaises(gh.GhError):
                convert_manifest("abc123")

    def test_raises_on_non_dict_response(self):
        with mock.patch.object(gh, "api", return_value=None):
            with self.assertRaises(gh.GhError):
                convert_manifest("abc123")


class ManifestTests(unittest.TestCase):
    def test_build_manifest_shape(self):
        m = build_manifest("interns-coder", "acme/widgets", "http://127.0.0.1:5/callback", "desc")
        self.assertEqual(m["name"], "interns-coder")
        self.assertEqual(m["url"], "https://github.com/acme/widgets")
        self.assertEqual(m["redirect_url"], "http://127.0.0.1:5/callback")
        self.assertFalse(m["public"])
        self.assertEqual(m["default_events"], [])
        self.assertEqual(m["default_permissions"], APP_PERMISSIONS)

    def test_settings_url_user_vs_org(self):
        self.assertEqual(settings_new_url("alice", False),
                         "https://github.com/settings/apps/new")
        self.assertEqual(settings_new_url("acme", True),
                         "https://github.com/organizations/acme/settings/apps/new")


CODER = next(s for s in APPS if s.key == "coder")


def _repo():
    return gh_admin.Repo(owner="acme", name="widgets", is_org=False)


def _confirm_sequence(*answers: bool):
    """A con.confirm stand-in that returns each answer in turn, by call order."""
    it = iter(answers)
    return lambda question, default=False: next(it)


class ReuseAppTests(unittest.TestCase):
    def test_flag_writes_variable_and_keeps_existing_key(self):
        con = Console(assume_yes=True)
        with mock.patch.multiple(apps.gh_admin, set_variable=mock.DEFAULT,
                                 set_secret=mock.DEFAULT) as m:
            use_existing_app(con, _repo(), CODER, "Iv1.aaa", "interns-coder",
                             existing_secrets=[CODER.key_secret])
        m["set_variable"].assert_called_once_with("acme/widgets", CODER.client_id_var, "Iv1.aaa")
        m["set_secret"].assert_not_called()
        self.assertTrue(any("install the coder App on acme/widgets" in n for n in con.manual))

    def test_flag_without_key_records_manual_under_yes(self):
        con = Console(assume_yes=True)
        with mock.patch.multiple(apps.gh_admin, set_variable=mock.DEFAULT,
                                 set_secret=mock.DEFAULT) as m:
            use_existing_app(con, _repo(), CODER, "Iv1.aaa", "interns-coder",
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
        prompted for the Client ID via use_existing_app's own fallback."""
        con = Console(assume_yes=False)
        con.confirm = _confirm_sequence(True)  # "already have it?"
        con.prompt = lambda q: "Iv1.existing"
        with mock.patch.object(apps, "ManifestServer") as server, \
             mock.patch.object(apps.webbrowser, "open"), \
             mock.patch.multiple(apps.gh_admin, set_variable=mock.DEFAULT, set_secret=mock.DEFAULT) as m:
            provision_app(con, _repo(), CODER, None, existing_secrets=[CODER.key_secret])
        server.assert_not_called()
        m["set_variable"].assert_called_once_with("acme/widgets", CODER.client_id_var, "Iv1.existing")

    def test_provision_mints_when_operator_says_no_existing_app(self):
        con = Console(assume_yes=False, dry_run=True)
        con.confirm = _confirm_sequence(False, True)  # "already have it?" then "create new?"
        provision_app(con, _repo(), CODER, None, existing_secrets=[])
        self.assertTrue(any("via manifest" in p for p in con.planned))

    def test_provision_records_manual_todo_when_operator_declines_both(self):
        con = Console(assume_yes=False, dry_run=True)
        con.confirm = _confirm_sequence(False, False)  # "already have it?" then "create new?"
        provision_app(con, _repo(), CODER, None, existing_secrets=[])
        self.assertFalse(any("via manifest" in p for p in con.planned))
        self.assertTrue(any(CODER.client_id_var in n for n in con.manual))

    def test_provision_skips_reuse_question_under_yes(self):
        """--yes has no one to ask -- it must fall straight to minting rather
        than silently answering the reuse question for the operator."""
        con = Console(assume_yes=True, dry_run=True)
        with mock.patch.object(apps, "ManifestServer"):
            provision_app(con, _repo(), CODER, None, existing_secrets=[])
        # dry_run short-circuits before ManifestServer is ever constructed;
        # the assertion that matters is the mint path, not this call.
        self.assertTrue(any("via manifest" in p for p in con.planned))


class MintFlowTests(unittest.TestCase):
    def _mint(self, con, existing_secrets):
        server = mock.MagicMock()
        server.__enter__.return_value = server
        server.base_url = "http://127.0.0.1:9"
        server.wait_for_code.return_value = "code123"
        conv = {"client_id": "Iv1.new", "slug": "interns-coder-acme", "pem": "PEM"}
        with mock.patch.object(apps, "ManifestServer", return_value=server), \
             mock.patch.object(apps, "convert_manifest", return_value=conv), \
             mock.patch.object(apps.webbrowser, "open") as opener, \
             mock.patch.multiple(apps.gh_admin, set_variable=mock.DEFAULT,
                                 set_secret=mock.DEFAULT) as m:
            provision_app(con, _repo(), CODER, None, existing_secrets=existing_secrets)
        return m, opener

    def test_mint_writes_key_then_client_id_and_opens_install_page(self):
        con = Console(assume_yes=True)
        m, opener = self._mint(con, [CODER.key_secret])
        m["set_secret"].assert_called_once_with("acme/widgets", CODER.key_secret, "PEM")
        m["set_variable"].assert_called_once_with("acme/widgets", CODER.client_id_var, "Iv1.new")
        self.assertTrue(any("overwrite secret" in p for p in con.planned))
        opener.assert_called_once_with("http://127.0.0.1:9")
        self.assertTrue(any("apps/interns-coder-acme/installations/new" in n for n in con.manual))

    def test_interactive_mint_opens_install_page_after_creation(self):
        con = Console(assume_yes=False)
        con.confirm = _confirm_sequence(False, True)
        _, opener = self._mint(con, None)
        self.assertEqual(opener.call_count, 2)
        opener.assert_called_with("https://github.com/apps/interns-coder-acme/installations/new")


class ReuseAppPromptTests(unittest.TestCase):
    def test_pasted_pem_is_written(self):
        con = Console(assume_yes=False)
        with mock.patch("interns_install.credentials.prompt_multiline_secret", return_value="PEM"), \
             mock.patch.object(apps.webbrowser, "open"), \
             mock.patch.multiple(apps.gh_admin, set_variable=mock.DEFAULT,
                                 set_secret=mock.DEFAULT) as m:
            use_existing_app(con, _repo(), CODER, "Iv1.aaa", "interns-coder", existing_secrets=[])
        m["set_secret"].assert_called_once_with("acme/widgets", CODER.key_secret, "PEM")

    def test_blank_pem_records_manual_step(self):
        con = Console(assume_yes=False)
        with mock.patch("interns_install.credentials.prompt_multiline_secret", return_value=""), \
             mock.patch.object(apps.webbrowser, "open"), \
             mock.patch.multiple(apps.gh_admin, set_variable=mock.DEFAULT,
                                 set_secret=mock.DEFAULT) as m:
            use_existing_app(con, _repo(), CODER, "Iv1.aaa", "interns-coder", existing_secrets=[])
        m["set_secret"].assert_not_called()
        self.assertTrue(any(CODER.key_secret in n for n in con.manual))

    def test_prompted_client_id_blank_skips(self):
        con = Console(assume_yes=False)
        con.prompt = lambda q: ""
        with mock.patch.multiple(apps.gh_admin, set_variable=mock.DEFAULT) as m:
            use_existing_app(con, _repo(), CODER, None, "interns-coder", existing_secrets=[])
        m["set_variable"].assert_not_called()
        self.assertTrue(con.manual)

    def test_missing_client_id_under_yes_records_manual_step(self):
        con = Console(assume_yes=True)
        with mock.patch.multiple(apps.gh_admin, set_variable=mock.DEFAULT) as m:
            use_existing_app(con, _repo(), CODER, None, "interns-coder", existing_secrets=[])
        m["set_variable"].assert_not_called()
        self.assertTrue(any("--coder-client-id" in n for n in con.manual))

    def test_dry_run_plans_variable_and_secret(self):
        con = Console(assume_yes=False, dry_run=True)
        use_existing_app(con, _repo(), CODER, "Iv1.aaa", "interns-coder", existing_secrets=[])
        self.assertEqual(len(con.planned), 2)


class SecretHelpersTests(unittest.TestCase):
    def test_write_secret_skips_set_in_dry_run(self):
        con = Console(dry_run=True)
        with mock.patch.object(apps.gh_admin, "set_secret") as set_secret:
            apps.write_secret(con, _repo(), "S", "v", None)
        set_secret.assert_not_called()
        self.assertEqual(con.planned, ["set secret S"])

    def test_write_secret_sets_and_reports_verb(self):
        con = Console()
        with mock.patch.object(apps.gh_admin, "set_secret") as set_secret:
            apps.write_secret(con, _repo(), "S", "v", ["S"])
        set_secret.assert_called_once_with("acme/widgets", "S", "v")
        self.assertEqual(con.planned, ["overwrite secret S"])


if __name__ == "__main__":
    unittest.main()
