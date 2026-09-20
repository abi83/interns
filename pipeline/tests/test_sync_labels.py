import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import sync_labels


class SyncLabelsTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.manifest_path = Path(self._tmpdir.name) / "labels.json"
        self.manifest_path.write_text(json.dumps({
            "version": 7,
            "labels": [
                {"name": "status:ready", "color": "0e8a16", "description": "go"},
                {"name": "pr:coding", "color": "0e8a16", "description": "on it"},
            ],
        }))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_creates_every_label_when_the_repo_has_none(self):
        with patch("pipeline.sync_labels.gh.label_list", return_value=[]), \
             patch("pipeline.sync_labels.gh.label_create") as create, \
             patch("pipeline.sync_labels.gh.label_edit") as edit:
            result = sync_labels.sync_labels("acme/widgets", str(self.manifest_path))
        create.assert_any_call("acme/widgets", "status:ready", "0e8a16", "go")
        create.assert_any_call("acme/widgets", "pr:coding", "0e8a16", "on it")
        edit.assert_not_called()
        self.assertIn("2 created, 0 updated, 0 unchanged", result)

    def test_updates_a_drifted_label_and_leaves_a_matching_one_alone(self):
        existing = [
            {"name": "status:ready", "color": "cccccc", "description": "go"},
            {"name": "pr:coding", "color": "0e8a16", "description": "on it"},
        ]
        with patch("pipeline.sync_labels.gh.label_list", return_value=existing), \
             patch("pipeline.sync_labels.gh.label_create") as create, \
             patch("pipeline.sync_labels.gh.label_edit") as edit:
            result = sync_labels.sync_labels("acme/widgets", str(self.manifest_path))
        edit.assert_called_once_with("acme/widgets", "status:ready", "0e8a16", "go")
        create.assert_not_called()
        self.assertIn("0 created, 1 updated, 1 unchanged", result)

    def test_case_insensitive_colour_compare_no_spurious_update(self):
        existing = [
            {"name": "status:ready", "color": "0E8A16", "description": "go"},
            {"name": "pr:coding", "color": "0e8a16", "description": "on it"},
        ]
        with patch("pipeline.sync_labels.gh.label_list", return_value=existing), \
             patch("pipeline.sync_labels.gh.label_edit") as edit:
            result = sync_labels.sync_labels("acme/widgets", str(self.manifest_path))
        edit.assert_not_called()
        self.assertIn("0 created, 0 updated, 2 unchanged", result)

    def test_fails_on_a_malformed_manifest(self):
        self.manifest_path.write_text(json.dumps({"nope": True}))
        with self.assertRaisesRegex(sync_labels.ManifestError, "malformed manifest"):
            sync_labels.sync_labels("acme/widgets", str(self.manifest_path))

    def test_fails_on_a_missing_manifest(self):
        with self.assertRaisesRegex(sync_labels.ManifestError, "no such manifest"):
            sync_labels.sync_labels("acme/widgets", str(self.manifest_path) + ".missing")


class MainTests(unittest.TestCase):
    def test_fails_when_gh_token_unset(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}, clear=True):
            self.assertEqual(sync_labels._main([]), 1)

    def test_fails_when_github_repository_unset(self):
        with patch.dict(os.environ, {"GH_TOKEN": "x"}, clear=True):
            self.assertEqual(sync_labels._main([]), 1)


if __name__ == "__main__":
    unittest.main()
