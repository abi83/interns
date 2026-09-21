import os
import unittest
from unittest.mock import patch

from pipeline import handle_pr_closed


class HandlePrClosedTests(unittest.TestCase):
    def test_merged_drops_in_progress_and_clears_the_pr_label(self):
        with patch("pipeline.handle_pr_closed.labels.set_pr_pipeline_label") as set_pr, \
             patch("pipeline.handle_pr_closed.labels.edit_issue_labels") as edit_issue, \
             patch("pipeline.handle_pr_closed.labels.set_issue_status") as set_issue, \
             patch("pipeline.handle_pr_closed.gh.issue_comment") as comment:
            handle_pr_closed.handle_pr_closed("acme/widgets", 8, 19, True)
        set_pr.assert_called_once_with("acme/widgets", 8)
        edit_issue.assert_called_once_with("acme/widgets", 19, remove=["status:in-progress"])
        set_issue.assert_not_called()
        comment.assert_not_called()

    def test_closed_unmerged_moves_the_issue_and_comments(self):
        with patch("pipeline.handle_pr_closed.labels.set_pr_pipeline_label"), \
             patch("pipeline.handle_pr_closed.labels.edit_issue_labels") as edit_issue, \
             patch("pipeline.handle_pr_closed.labels.set_issue_status") as set_issue, \
             patch("pipeline.handle_pr_closed.gh.issue_comment") as comment, \
             patch("pipeline.handle_pr_closed.actions_env.pr_url", return_value="https://github.com/acme/widgets/pull/8"), \
             patch("pipeline.handle_pr_closed.actions_env.run_url", return_value="https://x/runs/1"):
            handle_pr_closed.handle_pr_closed("acme/widgets", 8, 19, False)
        edit_issue.assert_not_called()
        set_issue.assert_called_once_with("acme/widgets", 19, "status:needs-attention")
        comment.assert_called_once()
        body = comment.call_args[0][2]
        self.assertIn("closed without merging", body)

    def test_no_linked_issue_only_clears_the_pr_label(self):
        with patch("pipeline.handle_pr_closed.labels.set_pr_pipeline_label") as set_pr, \
             patch("pipeline.handle_pr_closed.labels.edit_issue_labels") as edit_issue, \
             patch("pipeline.handle_pr_closed.labels.set_issue_status") as set_issue, \
             patch("pipeline.handle_pr_closed.gh.issue_comment") as comment:
            handle_pr_closed.handle_pr_closed("acme/widgets", 8, None, False)
        set_pr.assert_called_once_with("acme/widgets", 8)
        edit_issue.assert_not_called()
        set_issue.assert_not_called()
        comment.assert_not_called()


class CliTests(unittest.TestCase):
    def test_merged_false_is_parsed(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}), \
             patch("pipeline.handle_pr_closed.handle_pr_closed") as fn:
            handle_pr_closed._main(["8", "19", "false"])
        fn.assert_called_once_with("acme/widgets", 8, 19, False)

    def test_empty_issue_argument_is_treated_as_no_issue(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}), \
             patch("pipeline.handle_pr_closed.handle_pr_closed") as fn:
            handle_pr_closed._main(["8", "", "false"])
        fn.assert_called_once_with("acme/widgets", 8, None, False)

    def test_merged_true_is_parsed(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}), \
             patch("pipeline.handle_pr_closed.handle_pr_closed") as fn:
            handle_pr_closed._main(["8", "19", "true"])
        fn.assert_called_once_with("acme/widgets", 8, 19, True)


if __name__ == "__main__":
    unittest.main()
