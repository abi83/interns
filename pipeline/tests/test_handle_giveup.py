import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import handle_giveup


class HandleGiveupTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name)
        self.output_file = self.workspace / "output"
        self.output_file.write_text("")
        env = patch.dict(os.environ, {"GITHUB_OUTPUT": str(self.output_file)})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_no_sentinel_emits_gave_up_false_and_does_nothing(self):
        with patch("pipeline.handle_giveup.labels.set_issue_status") as set_issue, \
             patch("pipeline.handle_giveup.labels.set_pr_pipeline_label") as set_pr, \
             patch("pipeline.handle_giveup.gh.issue_comment") as comment:
            result = handle_giveup.handle_giveup("acme/widgets", 7, 15, str(self.workspace))
        self.assertFalse(result)
        self.assertEqual(self.output_file.read_text(), "gave_up=false\n")
        set_issue.assert_not_called()
        set_pr.assert_not_called()
        comment.assert_not_called()

    def test_sentinel_present_escalates_and_comments_the_reason(self):
        (self.workspace / handle_giveup.SENTINEL_NAME).write_text(
            "Feedback needs a change under .github/workflows/ which I cannot push.\n"
        )
        with patch("pipeline.handle_giveup.labels.set_issue_status") as set_issue, \
             patch("pipeline.handle_giveup.labels.set_pr_pipeline_label") as set_pr, \
             patch("pipeline.handle_giveup.gh.issue_comment") as comment, \
             patch("pipeline.handle_giveup.actions_env.run_url", return_value="https://x/runs/1"):
            result = handle_giveup.handle_giveup("acme/widgets", 7, 15, str(self.workspace))
        self.assertTrue(result)
        self.assertEqual(self.output_file.read_text(), "gave_up=true\n")
        set_pr.assert_called_once_with("acme/widgets", 15)
        set_issue.assert_called_once_with("acme/widgets", 7, "status:needs-attention")
        comment.assert_called_once()
        body = comment.call_args[0][2]
        self.assertIn("declined this task", body)
        self.assertIn("cannot push", body)
        self.assertIn("https://x/runs/1", body)

    def test_sentinel_present_but_empty_uses_placeholder_reason(self):
        (self.workspace / handle_giveup.SENTINEL_NAME).write_text("")
        with patch("pipeline.handle_giveup.labels.set_issue_status") as set_issue, \
             patch("pipeline.handle_giveup.labels.set_pr_pipeline_label") as set_pr, \
             patch("pipeline.handle_giveup.gh.issue_comment") as comment, \
             patch("pipeline.handle_giveup.actions_env.run_url", return_value="https://x/runs/1"):
            result = handle_giveup.handle_giveup("acme/widgets", 7, None, str(self.workspace))
        self.assertTrue(result)
        set_pr.assert_not_called()
        set_issue.assert_called_once_with("acme/widgets", 7, "status:needs-attention")
        body = comment.call_args[0][2]
        self.assertIn("no reason given", body)


class CliTests(unittest.TestCase):
    def test_empty_pr_argument_is_treated_as_no_pr(self):
        with patch("pipeline.handle_giveup.handle_giveup") as fn, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets", "GITHUB_WORKSPACE": "/ws", "GITHUB_OUTPUT": "/dev/null"}):
            handle_giveup._main(["7", ""])
        fn.assert_called_once_with("acme/widgets", 7, None, "/ws")

    def test_pr_argument_is_parsed_as_int(self):
        with patch("pipeline.handle_giveup.handle_giveup") as fn, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets", "GITHUB_WORKSPACE": "/ws", "GITHUB_OUTPUT": "/dev/null"}):
            handle_giveup._main(["7", "15"])
        fn.assert_called_once_with("acme/widgets", 7, 15, "/ws")


if __name__ == "__main__":
    unittest.main()
