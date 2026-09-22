import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interns import derive_code_hints
from interns.ctx import ActionsCtx


class DeriveCodeHintsTests(unittest.TestCase):
    def test_type_coding_task_maps_to_feat_and_a_feat_branch(self):
        with patch("interns.derive_code_hints.labels.issue_labels", return_value=["type:coding-task", "status:ready"]), \
             patch("interns.derive_code_hints.gh.issue_view", return_value={"title": "Pass the coder deterministic commit-type hints"}):
            hint, branch = derive_code_hints.derive_code_hints("acme/widgets", 42)
        self.assertEqual(hint, "feat:")
        self.assertEqual(branch, "feat/issue-42-pass-the-coder-deterministic-commit-type")

    def test_type_bug_maps_to_fix_and_a_fix_branch(self):
        with patch("interns.derive_code_hints.labels.issue_labels", return_value=["type:bug", "status:ready"]), \
             patch("interns.derive_code_hints.gh.issue_view", return_value={"title": "Crash on empty input"}):
            hint, branch = derive_code_hints.derive_code_hints("acme/widgets", 42)
        self.assertEqual(hint, "fix:")
        self.assertEqual(branch, "fix/issue-42-crash-on-empty-input")

    def test_slug_strips_punctuation_collapses_separators_trims_trailing_dashes(self):
        with patch("interns.derive_code_hints.labels.issue_labels", return_value=["type:coding-task"]), \
             patch("interns.derive_code_hints.gh.issue_view", return_value={"title": "  Refine: the (refiner) -- stop!  "}):
            _, branch = derive_code_hints.derive_code_hints("acme/widgets", 42)
        self.assertEqual(branch, "feat/issue-42-refine-the-refiner-stop")

    def test_raises_when_no_implementable_type_label_is_present(self):
        with patch("interns.derive_code_hints.labels.issue_labels", return_value=["type:spike"]):
            with self.assertRaisesRegex(ValueError, "neither type:bug nor type:coding-task"):
                derive_code_hints.derive_code_hints("acme/widgets", 42)


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.output_file = Path(self._tmpdir.name) / "output"
        self.output_file.write_text("")
        self.ctx = ActionsCtx(repo="acme/widgets", token="", server_url="", run_id="",
                               run_attempt=1, workspace=".", event_name="",
                               reviewer_bot="", step_summary="")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_writes_the_hints_to_github_output(self):
        with patch("interns.derive_code_hints.derive_code_hints", return_value=("feat:", "feat/issue-42-x")), \
             patch.dict(os.environ, {"GITHUB_OUTPUT": str(self.output_file)}):
            status = derive_code_hints._main(self.ctx, ["--issue", "42"])
        self.assertEqual(status, 0)
        self.assertEqual(self.output_file.read_text(), "commit_type_hint=feat:\nbranch=feat/issue-42-x\n")

    def test_fails_when_no_implementable_type_label_is_present(self):
        with patch("interns.derive_code_hints.labels.issue_labels", return_value=["type:spike"]), \
             patch.dict(os.environ, {"GITHUB_OUTPUT": str(self.output_file)}):
            status = derive_code_hints._main(self.ctx, ["--issue", "42"])
        self.assertEqual(status, 1)
        self.assertEqual(self.output_file.read_text(), "")


if __name__ == "__main__":
    unittest.main()
