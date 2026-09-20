import unittest
from unittest.mock import patch

from pipeline import flag_failure


class FlagFailureTests(unittest.TestCase):
    def test_standard_failure_escalates_the_issue_and_comments(self):
        with patch("pipeline.flag_failure.labels.set_issue_status") as set_issue, \
             patch("pipeline.flag_failure.labels.escalate_pr") as escalate, \
             patch("pipeline.flag_failure.gh.issue_comment") as comment, \
             patch("pipeline.flag_failure.gh.run_url", return_value="https://x/runs/42"):
            flag_failure.flag_failure("acme/widgets", "implementation", 9, None, False)
        escalate.assert_not_called()
        set_issue.assert_called_once_with("acme/widgets", 9, "status:needs-attention")
        comment.assert_called_once_with("acme/widgets", 9, "Automated implementation failed. See the run: https://x/runs/42")

    def test_review_failure_comments_on_the_pr_not_the_issue(self):
        with patch("pipeline.flag_failure.labels.set_issue_status") as set_issue, \
             patch("pipeline.flag_failure.labels.escalate_pr") as escalate, \
             patch("pipeline.flag_failure.gh.pr_comment") as pr_comment, \
             patch("pipeline.flag_failure.gh.issue_comment") as issue_comment, \
             patch("pipeline.flag_failure.gh.run_url", return_value="https://x/runs/42"):
            flag_failure.flag_failure("acme/widgets", "review", 9, 4, False)
        escalate.assert_called_once_with("acme/widgets", 4)
        set_issue.assert_called_once_with("acme/widgets", 9, "status:needs-attention")
        pr_comment.assert_called_once_with("acme/widgets", 4, "Automated review failed. See the run: https://x/runs/42")
        issue_comment.assert_not_called()

    def test_fix_round_failure_posts_the_redispatch_command_on_the_issue(self):
        with patch("pipeline.flag_failure.labels.set_issue_status") as set_issue, \
             patch("pipeline.flag_failure.labels.set_pr_pipeline_label") as set_pr, \
             patch("pipeline.flag_failure.labels.escalate_pr") as escalate, \
             patch("pipeline.flag_failure.gh.issue_comment") as comment, \
             patch("pipeline.flag_failure.gh.pr_comment") as pr_comment, \
             patch("pipeline.flag_failure.gh.run_url", return_value="https://x/runs/42"):
            flag_failure.flag_failure("acme/widgets", "implementation", 9, 4, True)
        set_pr.assert_called_once_with("acme/widgets", 4)
        escalate.assert_not_called()
        set_issue.assert_called_once_with("acme/widgets", 9, "status:needs-attention")
        pr_comment.assert_not_called()
        comment.assert_called_once()
        body = comment.call_args[0][2]
        self.assertIn("gh workflow run code-pipeline.yml -f phase=coder -f issue_number=9 -f fix_round=true", body)
        self.assertNotIn("Automated implementation failed", body)

    def test_no_pr_and_no_issue_is_a_noop_before_the_comment(self):
        with patch("pipeline.flag_failure.labels.set_issue_status") as set_issue, \
             patch("pipeline.flag_failure.labels.escalate_pr") as escalate, \
             patch("pipeline.flag_failure.gh.issue_comment") as comment, \
             patch("pipeline.flag_failure.gh.run_url", return_value="https://x/runs/42"):
            with self.assertRaises(AssertionError):
                flag_failure.flag_failure("acme/widgets", "review", None, None, False)
        set_issue.assert_not_called()
        escalate.assert_not_called()
        comment.assert_not_called()


class CliTests(unittest.TestCase):
    def test_empty_issue_and_pr_are_treated_as_absent(self):
        import os
        with patch("pipeline.flag_failure.flag_failure") as fn, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}):
            flag_failure._main(["--noun", "review", "--pr", "4", "--issue", ""])
        fn.assert_called_once_with("acme/widgets", "review", None, 4, False)

    def test_fix_round_flag_is_parsed(self):
        import os
        with patch("pipeline.flag_failure.flag_failure") as fn, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}):
            flag_failure._main(["--noun", "implementation", "--issue", "9", "--pr", "4", "--fix-round"])
        fn.assert_called_once_with("acme/widgets", "implementation", 9, 4, True)

    def test_unknown_argument_is_rejected(self):
        with self.assertRaises(SystemExit):
            flag_failure._main(["--noun", "review", "--wat"])


if __name__ == "__main__":
    unittest.main()
