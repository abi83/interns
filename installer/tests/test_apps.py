import unittest

from interns_install.apps import (
    APP_PERMISSIONS,
    build_manifest,
    settings_new_url,
)


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


if __name__ == "__main__":
    unittest.main()
