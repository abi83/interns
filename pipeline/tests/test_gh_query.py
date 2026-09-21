import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from pipeline import gh_query


class GhQueryTests(unittest.TestCase):
    def test_head_ref_and_sha(self):
        with patch("pipeline.gh_query.gh.pr_view", return_value={"headRefName": "b", "headRefOid": "abc"}) as view:
            self.assertEqual(gh_query.head_ref("a/b", 3), "b")
            self.assertEqual(gh_query.head_sha("a/b", 3), "abc")
        view.assert_any_call("a/b", 3, ["headRefName"])
        view.assert_any_call("a/b", 3, ["headRefOid"])

    def test_closing_issue_first_or_empty(self):
        with patch("pipeline.gh_query.gh.pr_view", return_value={"closingIssuesReferences": [{"number": 9}, {"number": 10}]}):
            self.assertEqual(gh_query.closing_issue("a/b", 3), "9")
        with patch("pipeline.gh_query.gh.pr_view", return_value={"closingIssuesReferences": []}):
            self.assertEqual(gh_query.closing_issue("a/b", 3), "")

    def test_pr_for_issue_matches_closing_reference(self):
        prs = [
            {"number": 5, "headRefName": "one", "closingIssuesReferences": [{"number": 1}]},
            {"number": 6, "headRefName": "two", "closingIssuesReferences": [{"number": 2}]},
        ]
        with patch("pipeline.gh_query.gh.pr_list", return_value=prs):
            self.assertEqual(gh_query.pr_for_issue("a/b", 2), {"pr_number": "6", "head_ref": "two"})
            self.assertEqual(gh_query.pr_for_issue("a/b", 3), {"pr_number": "", "head_ref": ""})

    def test_main_prints_output_lines(self):
        prs = [{"number": 6, "headRefName": "two", "closingIssuesReferences": [{"number": 2}]}]
        out = io.StringIO()
        with patch("pipeline.gh_query.gh.pr_list", return_value=prs), redirect_stdout(out):
            gh_query._main(["a/b", "pr-for-issue", "2"])
        self.assertEqual(out.getvalue(), "pr_number=6\nhead_ref=two\n")
