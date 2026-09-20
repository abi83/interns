import unittest
from unittest.mock import patch

from pipeline import gh, spike_advisory


class PostAdvisoryTests(unittest.TestCase):
    def test_posts_the_advisory_on_an_estimated_spike(self):
        with patch("pipeline.spike_advisory.labels.issue_labels",
                   return_value=["type:spike", "status:estimated"]), \
             patch("pipeline.spike_advisory.gh.issue_comment") as comment:
            result = spike_advisory.post_advisory("acme/widgets", 34)
        comment.assert_called_once_with("acme/widgets", 34, spike_advisory.ADVISORY)
        self.assertEqual(result, spike_advisory.ADVISORY)

    def test_no_op_on_a_non_spike_issue_type(self):
        with patch("pipeline.spike_advisory.labels.issue_labels",
                   return_value=["type:coding-task", "status:refined"]), \
             patch("pipeline.spike_advisory.gh.issue_comment") as comment:
            result = spike_advisory.post_advisory("acme/widgets", 34)
        comment.assert_not_called()
        self.assertIsNone(result)

    def test_no_op_on_a_spike_not_yet_estimated(self):
        with patch("pipeline.spike_advisory.labels.issue_labels",
                   return_value=["type:spike", "status:in-progress"]), \
             patch("pipeline.spike_advisory.gh.issue_comment") as comment:
            result = spike_advisory.post_advisory("acme/widgets", 34)
        comment.assert_not_called()
        self.assertIsNone(result)

    def test_no_op_when_the_issue_has_no_labels_at_all(self):
        with patch("pipeline.spike_advisory.labels.issue_labels", return_value=[]), \
             patch("pipeline.spike_advisory.gh.issue_comment") as comment:
            result = spike_advisory.post_advisory("acme/widgets", 34)
        comment.assert_not_called()
        self.assertIsNone(result)

    def test_a_gh_failure_reading_labels_propagates(self):
        with patch("pipeline.spike_advisory.labels.issue_labels",
                   side_effect=gh.GhCommandError("boom")):
            with self.assertRaises(gh.GhCommandError):
                spike_advisory.post_advisory("acme/widgets", 34)


class CliTests(unittest.TestCase):
    def test_prints_a_message_when_not_an_advisory_case(self):
        import os
        from unittest.mock import patch as mock_patch
        with mock_patch("pipeline.spike_advisory.post_advisory", return_value=None), \
             mock_patch("builtins.print") as mock_print, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}):
            spike_advisory._main(["34"])
        mock_print.assert_called_once()

    def test_prints_nothing_when_advisory_posted(self):
        import os
        from unittest.mock import patch as mock_patch
        with mock_patch("pipeline.spike_advisory.post_advisory", return_value=spike_advisory.ADVISORY), \
             mock_patch("builtins.print") as mock_print, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}):
            spike_advisory._main(["34"])
        mock_print.assert_not_called()


if __name__ == "__main__":
    unittest.main()
