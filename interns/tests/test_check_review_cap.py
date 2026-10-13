import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interns.steps import check_review_cap
from interns.ctx import ActionsCtx
from interns.domain import lifecycle, lifecycle_apply
from interns.domain.verdict import Review, ReviewState


def reviews(n: int) -> list[Review]:
    return [Review(login="reviewer[bot]", state=ReviewState.CHANGES_REQUESTED, commit_id=f"sha{i}") for i in range(n)]


class CheckCapTests(unittest.TestCase):
    def check(self, n: int, **kwargs):
        with patch("interns.steps.check_review_cap.verdict.reviews_by", return_value=reviews(n)), \
             patch("interns.steps.check_review_cap.lifecycle_apply.apply") as apply:
            capped = check_review_cap.check_cap("acme/widgets", 12, "reviewer[bot]", 5, **kwargs)
        return capped, apply

    def test_under_the_cap_is_a_no_op(self):
        capped, apply = self.check(4)
        self.assertFalse(capped)
        apply.assert_not_called()

    def test_at_the_cap_fires_review_cap_reached(self):
        capped, apply = self.check(5, run_url="run")
        self.assertTrue(capped)
        apply.assert_called_once_with(
            "acme/widgets",
            lifecycle.decide(lifecycle.Event.REVIEW_CAP_REACHED, lifecycle.Facts(has_issue=False, has_pr=True)),
            pr=12, issue=None, words=lifecycle_apply.Words(run_url="run", detail="5"),
        )

    def test_over_the_cap_also_caps(self):
        capped, _ = self.check(7)
        self.assertTrue(capped)

    def test_a_given_count_skips_the_fetch(self):
        with patch("interns.steps.check_review_cap.verdict.reviews_by") as reviews_by, \
             patch("interns.steps.check_review_cap.lifecycle_apply.apply") as apply:
            capped = check_review_cap.check_cap("acme/widgets", 12, "reviewer[bot]", 5, count=5)
        self.assertTrue(capped)
        reviews_by.assert_not_called()
        apply.assert_called_once()


class CliTests(unittest.TestCase):
    def test_writes_capped_output_using_ctx(self):
        from interns.config import ReviewLoopConfig
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            ctx = ActionsCtx(repo="acme/widgets", token="", server_url="https://github.com")
            env = {"GITHUB_OUTPUT": output_file, "REVIEWER_BOT": "reviewer[bot]", "GITHUB_RUN_ID": "7"}
            with patch.dict(os.environ, env), \
                 patch("interns.steps.check_review_cap.config.load_raw", return_value={}), \
                 patch("interns.steps.check_review_cap.config.review_loop_config",
                       return_value=ReviewLoopConfig(max_fix_rounds=1, max_automatic_reviews=5)), \
                 patch("interns.steps.check_review_cap.check_cap", return_value=True) as fn:
                check_review_cap.main(ctx, ["--pr", "12"])
            fn.assert_called_once_with("acme/widgets", 12, "reviewer[bot]", 5, count=None,
                                        run_url="https://github.com/acme/widgets/actions/runs/7")
            self.assertEqual(Path(output_file).read_text(), "capped=true\n")


if __name__ == "__main__":
    unittest.main()
