import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interns.steps import check_review_cap
from interns.ctx import ActionsCtx
from interns.verdict import Review


class CheckCapTests(unittest.TestCase):
    def test_under_the_cap_is_a_no_op(self):
        reviews = [Review(login="reviewer[bot]", state="CHANGES_REQUESTED", commit_id=f"sha{i}") for i in range(4)]
        with patch("interns.steps.check_review_cap.verdict.reviews_by", return_value=reviews), \
             patch("interns.steps.check_review_cap.labels.escalate_pr") as escalate, \
             patch("interns.steps.check_review_cap.gh.pr_comment") as comment:
            capped = check_review_cap.check_cap("acme/widgets", 12, "reviewer[bot]", 5)
        self.assertFalse(capped)
        escalate.assert_not_called()
        comment.assert_not_called()

    def test_at_the_cap_escalates_and_comments(self):
        reviews = [Review(login="reviewer[bot]", state="CHANGES_REQUESTED", commit_id=f"sha{i}") for i in range(5)]
        with patch("interns.steps.check_review_cap.verdict.reviews_by", return_value=reviews), \
             patch("interns.steps.check_review_cap.labels.escalate_pr") as escalate, \
             patch("interns.steps.check_review_cap.gh.pr_comment") as comment:
            capped = check_review_cap.check_cap("acme/widgets", 12, "reviewer[bot]", 5)
        self.assertTrue(capped)
        escalate.assert_called_once_with("acme/widgets", 12)
        comment.assert_called_once()
        body = comment.call_args[0][2]
        self.assertIn("Automatic review limit (5) reached", body)

    def test_over_the_cap_also_caps(self):
        reviews = [Review(login="reviewer[bot]", state="CHANGES_REQUESTED", commit_id=f"sha{i}") for i in range(7)]
        with patch("interns.steps.check_review_cap.verdict.reviews_by", return_value=reviews), \
             patch("interns.steps.check_review_cap.labels.escalate_pr"), \
             patch("interns.steps.check_review_cap.gh.pr_comment"):
            self.assertTrue(check_review_cap.check_cap("acme/widgets", 12, "reviewer[bot]", 5))

    def test_a_given_count_skips_the_fetch(self):
        with patch("interns.steps.check_review_cap.verdict.reviews_by") as reviews_by, \
             patch("interns.steps.check_review_cap.labels.escalate_pr") as escalate, \
             patch("interns.steps.check_review_cap.gh.pr_comment"):
            capped = check_review_cap.check_cap("acme/widgets", 12, "reviewer[bot]", 5, count=5)
        self.assertTrue(capped)
        reviews_by.assert_not_called()
        escalate.assert_called_once_with("acme/widgets", 12)


class CliTests(unittest.TestCase):
    def test_writes_capped_output_using_ctx(self):
        from interns.config import ReviewLoopConfig
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            ctx = ActionsCtx(repo="acme/widgets", token="", server_url="", run_id="",
                             run_attempt=1, workspace=".", event_name="",
                             reviewer_bot="reviewer[bot]", step_summary="")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}), \
                 patch("interns.steps.check_review_cap.config.load_raw", return_value={}), \
                 patch("interns.steps.check_review_cap.config.review_loop_config",
                       return_value=ReviewLoopConfig(max_fix_rounds=1, max_automatic_reviews=5)), \
                 patch("interns.steps.check_review_cap.check_cap", return_value=True) as fn:
                check_review_cap._main(ctx, ["--pr", "12"])
            fn.assert_called_once_with("acme/widgets", 12, "reviewer[bot]", 5, count=None,
                                        run_url=ctx.run_url())
            self.assertEqual(Path(output_file).read_text(), "capped=true\n")


if __name__ == "__main__":
    unittest.main()
