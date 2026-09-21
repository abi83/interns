import os
import unittest
from unittest.mock import patch

from pipeline import preserve_issue_body


class PreserveIssueBodyTests(unittest.TestCase):
    def test_comments_body_in_details_block(self):
        with patch("pipeline.preserve_issue_body.gh.issue_comment") as comment:
            preserve_issue_body.preserve_issue_body("a/b", 4, "orig")
        comment.assert_called_once_with(
            "a/b", 4, "<details><summary>Body before refinement</summary>\n\norig\n\n</details>")

    def test_main_reads_body_from_env(self):
        with patch.dict(os.environ, {"ISSUE_BODY": "text"}), \
             patch("pipeline.preserve_issue_body.gh.issue_comment") as comment:
            preserve_issue_body._main(["a/b", "4"])
        self.assertIn("text", comment.call_args[0][2])
