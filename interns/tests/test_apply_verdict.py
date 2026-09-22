import unittest
from unittest.mock import patch

from interns import apply_verdict


class ApplyVerdictTests(unittest.TestCase):
    def test_approved_clears_the_pr_label_and_tells_the_issue(self):
        with patch("interns.apply_verdict.gh.pr_view", return_value={"headRefOid": "headsha"}), \
             patch("interns.apply_verdict.verdict.reviews_by", return_value=[
                 apply_verdict.verdict.Review(login="reviewer[bot]", state="APPROVED", commit_id="headsha"),
             ]), \
             patch("interns.apply_verdict.labels.set_pr_pipeline_label") as set_pr, \
             patch("interns.apply_verdict.gh.issue_comment") as comment:
            apply_verdict.apply_verdict("acme/widgets", 12, 34, "reviewer[bot]")
        set_pr.assert_called_once_with("acme/widgets", 12)
        comment.assert_called_once()
        self.assertIn("Reviewer approved", comment.call_args[0][2])

    def test_first_changes_requested_with_linked_issue_dispatches_a_fix_round(self):
        with patch("interns.apply_verdict.gh.pr_view", return_value={"headRefOid": "headsha"}), \
             patch("interns.apply_verdict.verdict.reviews_by", return_value=[
                 apply_verdict.verdict.Review(login="reviewer[bot]", state="CHANGES_REQUESTED", commit_id="headsha"),
             ]), \
             patch("interns.apply_verdict.labels.set_pr_pipeline_label") as set_pr, \
             patch("interns.apply_verdict.gh.dispatch_workflow") as dispatch:
            apply_verdict.apply_verdict("acme/widgets", 12, 34, "reviewer[bot]")
        set_pr.assert_called_once_with("acme/widgets", 12, "pr:coding")
        dispatch.assert_called_once_with(
            "acme/widgets", "code-pipeline.yml", None,
            {"phase": "coder", "issue_number": "34", "fix_round": "true"},
        )

    def test_second_changes_requested_escalates_without_dispatching(self):
        with patch("interns.apply_verdict.gh.pr_view", return_value={"headRefOid": "headsha"}), \
             patch("interns.apply_verdict.verdict.reviews_by", return_value=[
                 apply_verdict.verdict.Review(login="reviewer[bot]", state="CHANGES_REQUESTED", commit_id="oldsha"),
                 apply_verdict.verdict.Review(login="reviewer[bot]", state="CHANGES_REQUESTED", commit_id="headsha"),
             ]), \
             patch("interns.apply_verdict.labels.escalate_pr") as escalate, \
             patch("interns.apply_verdict.labels.set_issue_status") as set_issue, \
             patch("interns.apply_verdict.gh.pr_comment") as comment, \
             patch("interns.apply_verdict.gh.dispatch_workflow") as dispatch:
            apply_verdict.apply_verdict("acme/widgets", 12, 34, "reviewer[bot]")
        escalate.assert_called_once_with("acme/widgets", 12)
        set_issue.assert_called_once_with("acme/widgets", 34, "status:needs-attention")
        dispatch.assert_not_called()
        self.assertIn("didn't converge", comment.call_args[0][2])

    def test_changes_requested_with_no_linked_issue_cannot_dispatch(self):
        with patch("interns.apply_verdict.gh.pr_view", return_value={"headRefOid": "headsha"}), \
             patch("interns.apply_verdict.verdict.reviews_by", return_value=[
                 apply_verdict.verdict.Review(login="reviewer[bot]", state="CHANGES_REQUESTED", commit_id="headsha"),
             ]), \
             patch("interns.apply_verdict.labels.set_pr_pipeline_label") as set_pr, \
             patch("interns.apply_verdict.gh.pr_comment") as comment, \
             patch("interns.apply_verdict.gh.dispatch_workflow") as dispatch:
            apply_verdict.apply_verdict("acme/widgets", 12, None, "reviewer[bot]")
        set_pr.assert_called_once_with("acme/widgets", 12)
        dispatch.assert_not_called()
        self.assertIn("no linked issue", comment.call_args[0][2])

    def test_unrecognized_verdict_flags_for_a_human(self):
        with patch("interns.apply_verdict.gh.pr_view", return_value={"headRefOid": "headsha"}), \
             patch("interns.apply_verdict.verdict.reviews_by", return_value=[
                 apply_verdict.verdict.Review(login="reviewer[bot]", state="COMMENTED", commit_id="headsha"),
             ]), \
             patch("interns.apply_verdict.labels.escalate_pr") as escalate, \
             patch("interns.apply_verdict.labels.set_issue_status") as set_issue, \
             patch("interns.apply_verdict.gh.pr_comment") as comment:
            apply_verdict.apply_verdict("acme/widgets", 12, 34, "reviewer[bot]")
        escalate.assert_called_once_with("acme/widgets", 12)
        set_issue.assert_called_once_with("acme/widgets", 34, "status:needs-attention")
        self.assertIn("without submitting a recognized verdict", comment.call_args[0][2])

    def test_stale_review_against_an_earlier_commit_flags_for_a_human(self):
        with patch("interns.apply_verdict.gh.pr_view", return_value={"headRefOid": "headsha"}), \
             patch("interns.apply_verdict.verdict.reviews_by", return_value=[
                 apply_verdict.verdict.Review(login="reviewer[bot]", state="APPROVED", commit_id="oldsha"),
             ]), \
             patch("interns.apply_verdict.labels.escalate_pr"), \
             patch("interns.apply_verdict.labels.set_issue_status"), \
             patch("interns.apply_verdict.gh.pr_comment") as comment:
            apply_verdict.apply_verdict("acme/widgets", 12, 34, "reviewer[bot]")
        self.assertIn("without submitting a recognized verdict", comment.call_args[0][2])


if __name__ == "__main__":
    unittest.main()
