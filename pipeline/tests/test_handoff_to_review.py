import unittest
from unittest.mock import patch

from pipeline import handoff_to_review


class HandoffTests(unittest.TestCase):
    def test_hands_the_pr_to_the_reviewer_when_one_exists(self):
        with patch("pipeline.handoff_to_review.labels.set_pr_pipeline_label") as set_pr, \
             patch("pipeline.handoff_to_review.labels.set_issue_status") as set_issue, \
             patch("pipeline.handoff_to_review.gh.issue_comment") as comment:
            handoff_to_review.handoff("acme/widgets", 7, 15)
        set_pr.assert_called_once_with("acme/widgets", 15, "pr:in-review")
        set_issue.assert_not_called()
        comment.assert_not_called()

    def test_flags_the_issue_when_the_coder_left_no_pr(self):
        with patch("pipeline.handoff_to_review.labels.set_pr_pipeline_label") as set_pr, \
             patch("pipeline.handoff_to_review.labels.set_issue_status") as set_issue, \
             patch("pipeline.handoff_to_review.gh.issue_comment") as comment, \
             patch("pipeline.handoff_to_review.gh.run_url", return_value="https://x/runs/1"):
            handoff_to_review.handoff("acme/widgets", 7, None)
        set_pr.assert_not_called()
        set_issue.assert_called_once_with("acme/widgets", 7, "status:needs-attention")
        comment.assert_called_once()
        args = comment.call_args[0]
        self.assertEqual(args[:2], ("acme/widgets", 7))
        self.assertIn("without leaving an open PR referencing this issue", args[2])
        self.assertIn("https://x/runs/1", args[2])

    def test_a_gh_failure_setting_the_pr_label_propagates(self):
        # Best-effort label edits are handled inside pipeline.labels itself;
        # this module doesn't swallow anything on top of that.
        with patch("pipeline.handoff_to_review.labels.set_pr_pipeline_label",
                   side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                handoff_to_review.handoff("acme/widgets", 7, 15)


class CliTests(unittest.TestCase):
    def test_empty_string_pr_is_treated_as_no_pr(self):
        import os
        with patch("pipeline.handoff_to_review.handoff") as handoff_fn, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}):
            handoff_to_review._main(["7", ""])
        handoff_fn.assert_called_once_with("acme/widgets", 7, None)

    def test_pr_argument_is_parsed_as_int(self):
        import os
        with patch("pipeline.handoff_to_review.handoff") as handoff_fn, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}):
            handoff_to_review._main(["7", "15"])
        handoff_fn.assert_called_once_with("acme/widgets", 7, 15)


if __name__ == "__main__":
    unittest.main()
