import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import gate_issue_type


class GateTests(unittest.TestCase):
    def test_accepts_when_a_label_matches(self):
        with patch("pipeline.gate_issue_type.labels.issue_labels", return_value=["type:coding-task", "status:refined"]), \
             patch("pipeline.gate_issue_type.labels.edit_issue_labels") as edit, \
             patch("pipeline.gate_issue_type.gh.issue_comment") as comment:
            ok = gate_issue_type.gate("acme/widgets", 42, ["type:coding-task", "type:bug"], "status:refined", "nope")
        self.assertTrue(ok)
        edit.assert_not_called()
        comment.assert_not_called()

    def test_rejects_and_parks_the_issue(self):
        with patch("pipeline.gate_issue_type.labels.issue_labels", return_value=["type:epic", "status:refined"]), \
             patch("pipeline.gate_issue_type.labels.edit_issue_labels") as edit, \
             patch("pipeline.gate_issue_type.gh.issue_comment") as comment:
            ok = gate_issue_type.gate(
                "acme/widgets", 42, ["type:coding-task", "type:bug"], "status:refined", "Epics aren't sized directly.",
            )
        self.assertFalse(ok)
        edit.assert_called_once_with("acme/widgets", 42, add=["status:needs-attention"], remove=["status:refined"])
        comment.assert_called_once_with("acme/widgets", 42, "Epics aren't sized directly.")


class CliTests(unittest.TestCase):
    def test_writes_skip_false_on_accept(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            with patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets", "GITHUB_OUTPUT": output_file}), \
                 patch("pipeline.gate_issue_type.gate", return_value=True) as gate_fn:
                gate_issue_type._main(["42", "type:coding-task,type:bug", "status:refined", "nope"])
            gate_fn.assert_called_once_with("acme/widgets", 42, ["type:coding-task", "type:bug"], "status:refined", "nope")
            self.assertEqual(Path(output_file).read_text(), "skip=false\n")

    def test_writes_skip_true_on_reject(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            with patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets", "GITHUB_OUTPUT": output_file}), \
                 patch("pipeline.gate_issue_type.gate", return_value=False):
                gate_issue_type._main(["42", "type:coding-task", "status:refined", "nope"])
            self.assertEqual(Path(output_file).read_text(), "skip=true\n")


if __name__ == "__main__":
    unittest.main()
