import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import gather_fix_feedback
from pipeline.verdict import Review


class BuildFeedbackTextTests(unittest.TestCase):
    def test_builds_the_review_comments_and_conversation_block(self):
        review = Review(login="somedev", state="CHANGES_REQUESTED", commit_id="sha1",
                         id=123, submitted_at="2026-01-02T03:04:05Z", body="do the thing")
        comments = [{"pull_request_review_id": 123, "path": "a.py", "line": 10, "body": "fix this", "created_at": "2026-01-02T03:05:00Z"}]
        conversation = [{"created_at": "2026-01-02T04:00:00Z", "user": {"login": "somedev"}, "body": "looks good otherwise"}]

        def fake_pages(path):
            if "pulls" in path and "comments" in path:
                return comments
            return conversation

        with patch("pipeline.gather_fix_feedback.verdict.all_reviews", return_value=[review]), \
             patch("pipeline.gather_fix_feedback.gh.api_all_pages", side_effect=fake_pages):
            text = gather_fix_feedback.build_feedback_text("acme/widgets", 6)
        self.assertIn("Latest REQUEST_CHANGES review — 2026-01-02T03:04:05Z", text)
        self.assertIn("do the thing", text)
        self.assertIn("a.py:10\n  fix this", text)
        self.assertIn("somedev (2026-01-02T04:00:00Z)\nlooks good otherwise", text)

    def test_only_changes_requested_reviews_are_considered(self):
        reviews = [
            Review(login="somedev", state="APPROVED", commit_id="sha1", id=1, submitted_at="t1", body="lgtm"),
        ]
        with patch("pipeline.gather_fix_feedback.verdict.all_reviews", return_value=reviews):
            with self.assertRaises(gather_fix_feedback.NoChangesRequestedReviewError):
                gather_fix_feedback.build_feedback_text("acme/widgets", 6)

    def test_raises_when_there_is_no_changes_requested_review(self):
        with patch("pipeline.gather_fix_feedback.verdict.all_reviews", return_value=[]):
            with self.assertRaises(gather_fix_feedback.NoChangesRequestedReviewError):
                gather_fix_feedback.build_feedback_text("acme/widgets", 6)


class CliTests(unittest.TestCase):
    def test_no_pr_returns_failure_without_calling_git(self):
        with patch("pipeline.gather_fix_feedback.checkout_branch") as checkout, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}):
            rc = gather_fix_feedback._main(["", "some-branch", "5"])
        self.assertEqual(rc, 1)
        checkout.assert_not_called()

    def test_no_changes_requested_review_returns_failure(self):
        with patch("pipeline.gather_fix_feedback.checkout_branch"), \
             patch("pipeline.gather_fix_feedback.build_feedback_text",
                   side_effect=gather_fix_feedback.NoChangesRequestedReviewError("no CHANGES_REQUESTED review found for PR #6")), \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}):
            rc = gather_fix_feedback._main(["6", "feature-x", "5"])
        self.assertEqual(rc, 1)

    def test_writes_the_feedback_block_to_github_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            with patch("pipeline.gather_fix_feedback.checkout_branch") as checkout, \
                 patch("pipeline.gather_fix_feedback.build_feedback_text", return_value="## Latest REQUEST_CHANGES review — x"), \
                 patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets", "GITHUB_OUTPUT": output_file}):
                rc = gather_fix_feedback._main(["6", "feature-x", "5"])
            self.assertEqual(rc, 0)
            checkout.assert_called_once_with("feature-x")
            out = Path(output_file).read_text()
            self.assertRegex(out, r"^text<<ghadelim_[0-9a-f]+\n")
            self.assertIn("Latest REQUEST_CHANGES review — x", out)

    def test_delimiter_collision_in_review_text_does_not_truncate_output(self):
        # The exact bug class this was rewritten to avoid: a hardcoded
        # delimiter that happens to appear inside human-authored review text.
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            with patch("pipeline.gather_fix_feedback.checkout_branch"), \
                 patch("pipeline.gather_fix_feedback.build_feedback_text",
                       return_value="please fix this:\nghadelim_0000000000000000000000000000000\nthanks"), \
                 patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets", "GITHUB_OUTPUT": output_file}):
                rc = gather_fix_feedback._main(["6", "feature-x", "5"])
            self.assertEqual(rc, 0)
            out = Path(output_file).read_text()
            self.assertIn("ghadelim_0000000000000000000000000000000\nthanks", out)


if __name__ == "__main__":
    unittest.main()
