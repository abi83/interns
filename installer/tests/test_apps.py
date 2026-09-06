import io
import unittest
import urllib.error
import urllib.request
from unittest import mock

from interns_install import gh
from interns_install.apps import (
    APP_PERMISSIONS,
    ManifestServer,
    build_manifest,
    settings_new_url,
)


class ManifestTests(unittest.TestCase):
    def test_build_manifest_shape(self):
        m = build_manifest("interns-coder", "http://127.0.0.1:5/callback", "desc")
        self.assertEqual(m["name"], "interns-coder")
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
            lambda redirect: build_manifest("interns-reviewer", redirect, "d"),
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


class ConvertManifestTests(unittest.TestCase):
    def test_exchanges_code_without_authorization_header(self):
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["headers"] = req.headers
            captured["method"] = req.get_method()
            captured["url"] = req.full_url
            return io.BytesIO(b'{"id": 42, "pem": "-----KEY-----", "slug": "x"}')

        with mock.patch("urllib.request.urlopen", fake_urlopen):
            out = gh.convert_manifest("tok123")

        self.assertEqual(out["id"], 42)
        self.assertEqual(captured["method"], "POST")
        self.assertIn("app-manifest/tok123/conversions", captured["url"])
        self.assertNotIn("Authorization", captured["headers"])

    def test_http_error_becomes_ghError(self):
        def boom(req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

        with mock.patch("urllib.request.urlopen", boom), \
             self.assertRaises(gh.GhError):
            gh.convert_manifest("expired")


if __name__ == "__main__":
    unittest.main()
