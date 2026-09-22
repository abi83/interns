import unittest
from unittest.mock import patch

from interns import gh, verdict
from interns.verdict import Review


def _reviews_payload(entries: list[tuple[str, str, str]]) -> list[dict]:
    return [{"user": {"login": login}, "state": state, "commit_id": commit_id}
            for login, state, commit_id in entries]


class AllReviewsTests(unittest.TestCase):
    def test_includes_every_author(self):
        payload = _reviews_payload([
            ("somedev", "COMMENTED", "sha1"),
            ("reviewer[bot]", "CHANGES_REQUESTED", "sha1"),
        ])
        with patch("interns.gh.api_all_pages", return_value=payload):
            reviews = verdict.all_reviews("o/r", 12)
        self.assertEqual(reviews, [
            Review("somedev", "COMMENTED", "sha1"),
            Review("reviewer[bot]", "CHANGES_REQUESTED", "sha1"),
        ])

    def test_unexpected_payload_raises(self):
        with patch("interns.gh.api_all_pages", return_value={"not": "a list"}):
            with self.assertRaises(gh.GhCommandError):
                verdict.all_reviews("o/r", 12)


class ReviewsByTests(unittest.TestCase):
    def test_filters_to_the_given_login(self):
        payload = _reviews_payload([
            ("somedev", "COMMENTED", "sha1"),
            ("reviewer[bot]", "CHANGES_REQUESTED", "sha1"),
        ])
        with patch("interns.gh.api_all_pages", return_value=payload):
            reviews = verdict.reviews_by("o/r", 12, "reviewer[bot]")
        self.assertEqual(reviews, [Review("reviewer[bot]", "CHANGES_REQUESTED", "sha1")])

    def test_no_reviews_from_that_login(self):
        with patch("interns.gh.api_all_pages", return_value=_reviews_payload([("somedev", "COMMENTED", "sha1")])):
            self.assertEqual(verdict.reviews_by("o/r", 12, "reviewer[bot]"), [])

    def test_unexpected_payload_raises(self):
        with patch("interns.gh.api_all_pages", return_value={"not": "a list"}):
            with self.assertRaises(gh.GhCommandError):
                verdict.reviews_by("o/r", 12, "reviewer[bot]")


class VerdictForHeadTests(unittest.TestCase):
    def test_no_reviews_is_no_verdict(self):
        self.assertIsNone(verdict.verdict_for_head([], "head1"))

    def test_latest_review_against_current_head(self):
        reviews = [Review("reviewer[bot]", "CHANGES_REQUESTED", "head1")]
        self.assertEqual(verdict.verdict_for_head(reviews, "head1"), "CHANGES_REQUESTED")

    def test_stale_review_from_an_earlier_commit_is_no_verdict(self):
        # The exact edge case the bash dedup logic exists to handle: a fix was
        # pushed on top of a CHANGES_REQUESTED review, moving the head past
        # the commit that review targeted.
        reviews = [Review("reviewer[bot]", "CHANGES_REQUESTED", "oldsha")]
        self.assertIsNone(verdict.verdict_for_head(reviews, "newsha"))

    def test_only_the_latest_review_counts(self):
        reviews = [
            Review("reviewer[bot]", "CHANGES_REQUESTED", "head1"),
            Review("reviewer[bot]", "APPROVED", "head2"),
        ]
        self.assertEqual(verdict.verdict_for_head(reviews, "head2"), "APPROVED")
        self.assertIsNone(verdict.verdict_for_head(reviews, "head1"))


class RoundsRequestedTests(unittest.TestCase):
    def test_counts_changes_requested_only(self):
        reviews = [
            Review("reviewer[bot]", "COMMENTED", "sha1"),
            Review("reviewer[bot]", "CHANGES_REQUESTED", "sha2"),
            Review("reviewer[bot]", "APPROVED", "sha3"),
        ]
        self.assertEqual(verdict.rounds_requested(reviews), 1)

    def test_excludes_the_given_commit(self):
        reviews = [
            Review("reviewer[bot]", "CHANGES_REQUESTED", "head1"),
            Review("reviewer[bot]", "CHANGES_REQUESTED", "head2"),
        ]
        self.assertEqual(verdict.rounds_requested(reviews, exclude_commit="head2"), 1)

    def test_no_exclusion_counts_everything(self):
        reviews = [
            Review("reviewer[bot]", "CHANGES_REQUESTED", "head1"),
            Review("reviewer[bot]", "CHANGES_REQUESTED", "head2"),
        ]
        self.assertEqual(verdict.rounds_requested(reviews), 2)


if __name__ == "__main__":
    unittest.main()
