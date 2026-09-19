import unittest
import urllib.error
import urllib.request
from unittest import mock

from interns_install import apps, gh
from interns_install.apps import (
    APP_PERMISSIONS,
    APPS,
    ManifestServer,
    build_manifest,
    provision_app,
    settings_new_url,
    use_existing_app,
)
from interns_install.console import Console


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


class ManifestServerTests(unittest.TestCase):
    def _make(self):
        return ManifestServer(
            "https://github.com/settings/apps/new",
            lambda redirect: build_manifest("interns-reviewer", "acme/widgets", redirect, "d"),
        )

    def test_form_page_carries_state_and_manifest(self):
        with self._make() as server:
            body = urllib.request.urlopen(server.base_url, timeout=5).read().decode()
            self.assertIn(f"state={server.state}", body)
            self.assertIn("name=manifest", body)
            self.assertIn(f"127.0.0.1:{server.port}/callback", server.manifest["redirect_url"])

    def test_callback_captures_code(self):
        with self._make() as server:
            url = f"{server.base_url}callback?code=abc123&state={server.state}"
            urllib.request.urlopen(url, timeout=5).read()
            self.assertEqual(server.wait_for_code(timeout=2), "abc123")

    def test_callback_rejects_bad_state(self):
        with self._make() as server:
            url = f"{server.base_url}callback?code=abc123&state=wrong"
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(url, timeout=5)
            self.assertEqual(ctx.exception.code, 400)
            with self.assertRaises(TimeoutError):
                server.wait_for_code(timeout=1)


CODER = next(s for s in APPS if s.key == "coder")


def _repo():
    return gh.Repo(owner="acme", name="widgets", is_org=False)


def _confirm_sequence(*answers: bool):
    """A con.confirm stand-in that returns each answer in turn, by call order."""
    it = iter(answers)
    return lambda question, default=False: next(it)


class ReuseAppTests(unittest.TestCase):
    def test_flag_writes_variable_and_keeps_existing_key(self):
        con = Console(assume_yes=True)
        with mock.patch.multiple(apps.gh, set_variable=mock.DEFAULT,
                                 set_secret=mock.DEFAULT) as m:
            use_existing_app(con, _repo(), CODER, "Iv1.aaa", "interns-coder",
                             existing_secrets=[CODER.key_secret])
        m["set_variable"].assert_called_once_with("acme/widgets", CODER.client_id_var, "Iv1.aaa")
        m["set_secret"].assert_not_called()
        self.assertTrue(any("installed on acme/widgets" in n for n in con.manual))

    def test_flag_without_key_records_manual_under_yes(self):
        con = Console(assume_yes=True)
        with mock.patch.multiple(apps.gh, set_variable=mock.DEFAULT,
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
             mock.patch.multiple(apps.gh, set_variable=mock.DEFAULT, set_secret=mock.DEFAULT) as m:
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
        with mock.patch.object(apps, "ManifestServer") as server:
            provision_app(con, _repo(), CODER, None, existing_secrets=[])
        # dry_run short-circuits before ManifestServer is ever constructed;
        # the assertion that matters is the mint path, not this call.
        self.assertTrue(any("via manifest" in p for p in con.planned))


if __name__ == "__main__":
    unittest.main()
