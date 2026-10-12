import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interns import cli
from interns.domain.issues import Comment, Issue
from interns.steps import fetch_issue


def _issue(body="B", comments=()):
    return Issue(number=1, title="T", body=body, state="OPEN", labels=[], comments=list(comments))


class WriteGithubOutputTests(unittest.TestCase):
    def _write(self, issue: Issue) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            out.write_text("")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}):
                fetch_issue.write_github_output(issue)
            return out.read_text()

    def test_writes_fields_and_comments(self):
        issue = Issue(
            number=5, title="My issue", body="# Body\nContent", state="OPEN", labels=["bug", "priority:high"],
            comments=[Comment("alice", "2024-01-01T00:00:00Z", "Nice")],
        )
        content = self._write(issue)
        for expected in ("number=5", "title=My issue", "labels=bug, priority:high", "# Body", "Nice"):
            self.assertIn(expected, content)

    def test_no_comments(self):
        content = self._write(_issue())
        self.assertNotIn("COMMENTS", content)

    def test_delimiter_in_body_cannot_inject(self):
        body = "intro\nEOF_BODY\nsome_output=injected\nEOF_COMMENTS\nmore"
        lines = self._write(_issue(body=body, comments=[Comment("alice", "2024-01-01T00:00:00Z", body)])).split("\n")
        header = next(line for line in lines if line.startswith("body<<"))
        start = lines.index(header)
        end = lines.index(header.removeprefix("body<<"), start + 1)
        self.assertEqual("\n".join(lines[start + 1 : end]), body)

    def test_without_github_output_raises(self):
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"}
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(cli.MissingEnvError):
                fetch_issue.write_github_output(_issue())


if __name__ == "__main__":
    unittest.main()
