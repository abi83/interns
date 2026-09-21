import unittest
from unittest.mock import patch

from pipeline import gh, verdict
from pipeline.verdict import Review


def _reviews_payload(entries: list[tuple[str, str, str]]) -> list[dict]:
    return [{"user": {"login": login}, "state": state, "commit_id": commit_id}
            for login, state, commit_id in entries]


class AllReviewsTests(unittest.TestCase):
    def test_includes_every_author(self):
        payload = _reviews_payload([
            ("somedev", "COMMENTED", "sha1"),
            ("reviewer[bot]", "CHANGES_REQUESTED", "sha1"),
        ])
        with patch("pipeline.gh.api_all_pages", return_value=payload):
            reviews = verdict.all_reviews("o/r", 12)
        self.assertEqual(reviews, [
            Review("somedev", "COMMENTED", "sha1"),
            Review("reviewer[bot]", "CHANGES_REQUESTED", "sha1"),
        ])

    def test_unexpected_payload_raises(self):
        with patch("pipeline.gh.api_all_pages", return_value={"not": "a list"}):
            with self.assertRaises(gh.GhCommandError):
                verdict.all_reviews("o/r", 12)


class ReviewsByTests(unittest.TestCase):
    def test_filters_to_the_given_login(self):
        payload = _reviews_payload([
            ("somedev", "COMMENTED", "sha1"),
            ("reviewer[bot]", "CHANGES_REQUESTED", "sha1"),
        ])
        with patch("pipeline.gh.api_all_pages", return_value=payload):
            reviews = verdict.reviews_by("o/r", 12, "reviewer[bot]")
        self.assertEqual(reviews, [Review("reviewer[bot]", "CHANGES_REQUESTED", "sha1")])

    def test_no_reviews_from_that_login(self):
        with patch("pipeline.gh.api_all_pages", return_value=_reviews_payload([("somedev", "COMMENTED", "sha1")])):
            self.assertEqual(verdict.reviews_by("o/r", 12, "reviewer[bot]"), [])

    def test_unexpected_payload_raises(self):
        with patch("pipeline.gh.api_all_pages", return_value={"not": "a list"}):
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


class CliTests(unittest.TestCase):
    def test_verdict_for_head_prints_empty_for_a_stale_review(self):
        payload = _reviews_payload([("reviewer[bot]", "CHANGES_REQUESTED", "oldsha")])
        with patch("pipeline.gh.api_all_pages", return_value=payload), patch("builtins.print") as mock_print:
            verdict._main(["o/r", "12", "reviewer[bot]", "verdict-for-head", "newsha"])
        mock_print.assert_called_once_with("")

    def test_rounds_requested_with_exclude_commit(self):
        payload = _reviews_payload([
            ("reviewer[bot]", "CHANGES_REQUESTED", "head1"),
            ("reviewer[bot]", "CHANGES_REQUESTED", "head2"),
        ])
        with patch("pipeline.gh.api_all_pages", return_value=payload), patch("builtins.print") as mock_print:
            verdict._main(["o/r", "12", "reviewer[bot]", "rounds-requested", "--exclude-commit", "head2"])
        mock_print.assert_called_once_with(1)

    def test_review_count(self):
        payload = _reviews_payload([("reviewer[bot]", "APPROVED", "sha1")])
        with patch("pipeline.gh.api_all_pages", return_value=payload), patch("builtins.print") as mock_print:
            verdict._main(["o/r", "12", "reviewer[bot]", "review-count"])
        mock_print.assert_called_once_with(1)

    def test_summary_for_head_prints_verdict_and_count_from_one_fetch(self):
        payload = _reviews_payload([
            ("reviewer[bot]", "CHANGES_REQUESTED", "oldsha"),
            ("reviewer[bot]", "APPROVED", "head1"),
        ])
        with patch("pipeline.gh.api_all_pages", return_value=payload) as api, patch("builtins.print") as mock_print:
            verdict._main(["o/r", "12", "reviewer[bot]", "summary-for-head", "head1"])
        api.assert_called_once()
        mock_print.assert_any_call("verdict=APPROVED")
        mock_print.assert_any_call("count=2")

    def test_summary_for_head_empty_verdict_for_a_stale_review(self):
        payload = _reviews_payload([("reviewer[bot]", "APPROVED", "oldsha")])
        with patch("pipeline.gh.api_all_pages", return_value=payload), patch("builtins.print") as mock_print:
            verdict._main(["o/r", "12", "reviewer[bot]", "summary-for-head", "head1"])
        mock_print.assert_any_call("verdict=")
        mock_print.assert_any_call("count=1")


if __name__ == "__main__":
    unittest.main()
