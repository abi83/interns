import unittest
from unittest.mock import patch

from interns.domain import lifecycle, lifecycle_apply, review_cap
from interns.domain.verdict import Review, ReviewState


def reviews(n: int) -> list[Review]:
    return [Review(login="reviewer[bot]", state=ReviewState.CHANGES_REQUESTED, commit_id=f"sha{i}") for i in range(n)]


class CheckCapTests(unittest.TestCase):
    def check(self, n: int, **kwargs):
        with patch("interns.domain.review_cap.verdict.reviews_by", return_value=reviews(n)), \
             patch("interns.domain.review_cap.lifecycle_apply.apply") as apply:
            capped = review_cap.check_cap("acme/widgets", 12, "reviewer[bot]", 5, **kwargs)
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
        with patch("interns.domain.review_cap.verdict.reviews_by") as reviews_by, \
             patch("interns.domain.review_cap.lifecycle_apply.apply") as apply:
            capped = review_cap.check_cap("acme/widgets", 12, "reviewer[bot]", 5, count=5)
        self.assertTrue(capped)
        reviews_by.assert_not_called()
        apply.assert_called_once()


if __name__ == "__main__":
    unittest.main()
