import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import fetch_issue
from pipeline.fetch_issue import Comment, Issue

GRAPHQL_RESPONSE = {
    "data": {
        "repository": {
            "issue": {
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
        }
    }
}


def _issue(body="B", comments=()):
    return Issue(number=1, title="T", body=body, state="OPEN", labels=[], comments=list(comments))


class FetchIssueTests(unittest.TestCase):
    def test_parses_response(self):
        with patch("pipeline.fetch_issue.gh.graphql", return_value=GRAPHQL_RESPONSE) as graphql:
            issue = fetch_issue.fetch_issue("owner/repo", 42)
        graphql.assert_called_once_with(fetch_issue._VIEW_QUERY, owner="owner", repo="repo", number=42)
        self.assertEqual(issue.number, 42)
        self.assertEqual(issue.labels, ["bug", "priority:high"])
        self.assertEqual([c.author for c in issue.comments], ["alice", "github-actions"])
        self.assertEqual(issue.parent.number, 10)
        self.assertEqual(len(issue.sub_issues), 1)
        self.assertEqual(issue.blocked_by, [])

    def test_null_body_and_no_parent(self):
        response = copy.deepcopy(GRAPHQL_RESPONSE)
        response["data"]["repository"]["issue"].update(body=None, parent=None)
        with patch("pipeline.fetch_issue.gh.graphql", return_value=response):
            issue = fetch_issue.fetch_issue("owner/repo", 42)
        self.assertEqual(issue.body, "")
        self.assertIsNone(issue.parent)


class WriteGithubOutputTests(unittest.TestCase):
    def _write(self, issue: Issue) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            out.write_text("")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}):
                fetch_issue.write_github_output(issue)
            return out.read_text()

    def test_writes_fields_and_excludes_bot_comments(self):
        issue = Issue(
            number=5, title="My issue", body="# Body\nContent", state="OPEN", labels=["bug", "priority:high"],
            comments=[
                Comment("alice", "2024-01-01T00:00:00Z", "Nice"),
                Comment("github-actions", "2024-01-02T00:00:00Z", "Bot"),
            ],
        )
        content = self._write(issue)
        for expected in ("number=5", "title=My issue", "labels=bug, priority:high", "# Body", "Nice"):
            self.assertIn(expected, content)
        self.assertNotIn("Bot", content)

    def test_no_human_comments(self):
        content = self._write(_issue(comments=[Comment("github-actions", "2024-01-01T00:00:00Z", "Auto")]))
        self.assertNotIn("Auto", content)

    def test_delimiter_in_body_cannot_inject(self):
        body = "intro\nEOF_BODY\nsome_output=injected\nEOF_COMMENTS\nmore"
        lines = self._write(_issue(body=body, comments=[Comment("alice", "2024-01-01T00:00:00Z", body)])).split("\n")
        header = next(line for line in lines if line.startswith("body<<"))
        start = lines.index(header)
        end = lines.index(header.removeprefix("body<<"), start + 1)
        self.assertEqual("\n".join(lines[start + 1 : end]), body)

    def test_without_github_output_prints(self):
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"}
        with patch.dict(os.environ, env, clear=True):
            fetch_issue.write_github_output(_issue())


if __name__ == "__main__":
    unittest.main()
