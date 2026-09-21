import unittest
from unittest.mock import patch

from pipeline import route_red_checks


class RouteRedChecksTests(unittest.TestCase):
    def test_marks_the_pr_needs_attention_comments_and_flags_the_linked_issue(self):
        with patch("pipeline.route_red_checks.labels.escalate_pr") as escalate, \
             patch("pipeline.route_red_checks.labels.set_issue_status") as set_issue, \
             patch("pipeline.route_red_checks.gh.pr_comment") as comment, \
             patch("pipeline.route_red_checks.actions_env.run_url", return_value="https://x/runs/1"):
            route_red_checks.route_red_checks("acme/widgets", 8, 19, "red checks: lint=fail")
        escalate.assert_called_once_with("acme/widgets", 8)
        set_issue.assert_called_once_with("acme/widgets", 19, "status:needs-attention")
        comment.assert_called_once()
        body = comment.call_args[0][2]
        self.assertIn("PR checks are not green (red checks: lint=fail)", body)
        self.assertIn("https://x/runs/1", body)

    def test_skips_the_issue_edit_when_there_is_no_linked_issue(self):
        with patch("pipeline.route_red_checks.labels.escalate_pr"), \
             patch("pipeline.route_red_checks.labels.set_issue_status") as set_issue, \
             patch("pipeline.route_red_checks.gh.pr_comment"), \
             patch("pipeline.route_red_checks.actions_env.run_url", return_value="https://x/runs/1"):
            route_red_checks.route_red_checks("acme/widgets", 8, None, "timed out")
        set_issue.assert_not_called()


class CliTests(unittest.TestCase):
    def test_empty_issue_argument_is_treated_as_no_issue(self):
        import os
        with patch("pipeline.route_red_checks.route_red_checks") as fn, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}):
            route_red_checks._main(["8", "", "timed out"])
        fn.assert_called_once_with("acme/widgets", 8, None, "timed out")

    def test_issue_argument_is_parsed_as_int(self):
        import os
        with patch("pipeline.route_red_checks.route_red_checks") as fn, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}):
            route_red_checks._main(["8", "19", "red checks: lint=fail"])
        fn.assert_called_once_with("acme/widgets", 8, 19, "red checks: lint=fail")


if __name__ == "__main__":
    unittest.main()
