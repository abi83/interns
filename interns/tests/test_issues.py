import copy
import unittest
from unittest.mock import patch

from interns.domain import issues

ISSUE_NODE = {
    "number": 42,
    "title": "Test issue",
    "body": "Issue body",
    "state": "OPEN",
    "labels": {"nodes": [{"name": "bug"}, {"name": "priority:high"}]},
    "comments": {
        "nodes": [
            {"author": {"login": "alice"}, "createdAt": "2024-01-01T00:00:00Z", "body": "Great issue"},
            {"author": {"login": "github-actions"}, "createdAt": "2024-01-02T00:00:00Z", "body": "Pipeline comment"},
        ]
    },
    "parent": {"number": 10, "title": "Parent epic", "state": "OPEN"},
    "subIssues": {"nodes": [{"number": 43, "title": "Sub", "state": "OPEN"}]},
    "blockedBy": {"nodes": []},
    "blocking": {"nodes": []},
}


class FetchIssueTests(unittest.TestCase):
    def test_parses_response(self):
        with patch("interns.domain.issues.gh.issue_with_relations", return_value=ISSUE_NODE) as view:
            issue = issues.fetch_issue("owner/repo", 42)
        view.assert_called_once_with("owner/repo", 42)
        self.assertEqual(issue.number, 42)
        self.assertEqual(issue.labels, ["bug", "priority:high"])
        self.assertEqual([c.author for c in issue.comments], ["alice"])
        assert issue.parent is not None
        self.assertEqual(issue.parent.number, 10)
        self.assertEqual(len(issue.sub_issues), 1)
        self.assertEqual(issue.blocked_by, [])

    def test_null_comment_author(self):
        response = copy.deepcopy(ISSUE_NODE)
        response["comments"]["nodes"].append(
            {"author": None, "createdAt": "2024-01-03T00:00:00Z", "body": "From deleted account"}
        )
        with patch("interns.domain.issues.gh.issue_with_relations", return_value=response):
            issue = issues.fetch_issue("owner/repo", 42)
        self.assertEqual(issue.comments[-1].author, "ghost")
        self.assertEqual(issue.comments[-1].body, "From deleted account")

    def test_excludes_pipeline_comments(self):
        with patch("interns.domain.issues.gh.issue_with_relations", return_value=ISSUE_NODE):
            issue = issues.fetch_issue("owner/repo", 42)
        self.assertNotIn("Pipeline comment", [c.body for c in issue.comments])

    def test_null_body_and_no_parent(self):
        response = copy.deepcopy(ISSUE_NODE)
        response.update(body=None, parent=None)
        with patch("interns.domain.issues.gh.issue_with_relations", return_value=response):
            issue = issues.fetch_issue("owner/repo", 42)
        self.assertEqual(issue.body, "")
        self.assertIsNone(issue.parent)


if __name__ == "__main__":
    unittest.main()
