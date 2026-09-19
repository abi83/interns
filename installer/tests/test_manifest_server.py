import unittest
import urllib.error
import urllib.request

from interns_install.apps import build_manifest
from interns_install.manifest_server import ManifestServer


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


if __name__ == "__main__":
    unittest.main()
