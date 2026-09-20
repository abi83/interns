import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import check_review_cap
from pipeline.verdict import Review


class CheckCapTests(unittest.TestCase):
    def test_under_the_cap_is_a_no_op(self):
        reviews = [Review(login="reviewer[bot]", state="CHANGES_REQUESTED", commit_id=f"sha{i}") for i in range(4)]
        with patch("pipeline.check_review_cap.verdict.reviews_by", return_value=reviews), \
             patch("pipeline.check_review_cap.labels.escalate_pr") as escalate, \
             patch("pipeline.check_review_cap.gh.pr_comment") as comment:
            capped = check_review_cap.check_cap("acme/widgets", 12, "reviewer[bot]", 5)
        self.assertFalse(capped)
        escalate.assert_not_called()
        comment.assert_not_called()

    def test_at_the_cap_escalates_and_comments(self):
        reviews = [Review(login="reviewer[bot]", state="CHANGES_REQUESTED", commit_id=f"sha{i}") for i in range(5)]
        with patch("pipeline.check_review_cap.verdict.reviews_by", return_value=reviews), \
             patch("pipeline.check_review_cap.labels.escalate_pr") as escalate, \
             patch("pipeline.check_review_cap.gh.pr_comment") as comment, \
             patch("pipeline.check_review_cap.gh.run_url", return_value="https://x/runs/1"):
            capped = check_review_cap.check_cap("acme/widgets", 12, "reviewer[bot]", 5)
        self.assertTrue(capped)
        escalate.assert_called_once_with("acme/widgets", 12)
        comment.assert_called_once()
        body = comment.call_args[0][2]
        self.assertIn("Automatic review limit (5) reached", body)

    def test_over_the_cap_also_caps(self):
        reviews = [Review(login="reviewer[bot]", state="CHANGES_REQUESTED", commit_id=f"sha{i}") for i in range(7)]
        with patch("pipeline.check_review_cap.verdict.reviews_by", return_value=reviews), \
             patch("pipeline.check_review_cap.labels.escalate_pr"), \
             patch("pipeline.check_review_cap.gh.pr_comment"), \
             patch("pipeline.check_review_cap.gh.run_url", return_value="https://x/runs/1"):
            self.assertTrue(check_review_cap.check_cap("acme/widgets", 12, "reviewer[bot]", 5))


class CliTests(unittest.TestCase):
    def test_writes_capped_output_using_env_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            with patch.dict(os.environ, {
                "GITHUB_REPOSITORY": "acme/widgets", "GITHUB_OUTPUT": output_file, "REVIEWER_BOT": "reviewer[bot]",
            }, clear=False), \
                 patch("pipeline.check_review_cap.check_cap", return_value=True) as fn:
                check_review_cap._main(["12"])
            fn.assert_called_once_with("acme/widgets", 12, "reviewer[bot]", 5)
            self.assertEqual(Path(output_file).read_text(), "capped=true\n")


if __name__ == "__main__":
    unittest.main()
