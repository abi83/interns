#!/usr/bin/env python3
"""Fetch a single issue via GraphQL and write fields to $GITHUB_OUTPUT.

Usage: python3 fetch-issue.py <issue_number>

Replaces the three separate `gh issue view` bash calls in resolve-issue so that
labels are also included and all issue data comes from one GraphQL round-trip.

Keep _VIEW_QUERY in sync with the copy in .github/scripts/gh-issues-mcp/server.py.
"""

import json
import os
import subprocess
import sys

_VIEW_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      number
      title
      body
      state
      labels(first: 20) { nodes { name } }
      comments(first: 50) {
        nodes { author { login } createdAt body }
      }
      parent          { number title state }
      subIssues(first: 20) { nodes { number title state } }
      blockedBy(first: 20) { nodes { number title state } }
      blocking(first: 20)  { nodes { number title state } }
    }
  }
}
"""

_REPO = os.environ.get("GITHUB_REPOSITORY", "")
_OUTPUT = os.environ.get("GITHUB_OUTPUT", "")


def _write(key: str, value: str, multiline: bool = False) -> None:
    if not _OUTPUT:
        print(f"{key}={value!r}")
        return
    with open(_OUTPUT, "a") as f:
        if multiline:
            sentinel = f"EOF_{key.upper()}"
            f.write(f"{key}<<{sentinel}\n{value}\n{sentinel}\n")
        else:
            f.write(f"{key}={value}\n")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: fetch-issue.py <issue_number>")

    number = int(sys.argv[1])
    owner, repo = _REPO.split("/", 1)

    result = subprocess.run(
        [
            "gh", "api", "graphql",
            "-f", f"query={_VIEW_QUERY}",
            "-F", f"owner={owner}",
            "-F", f"repo={repo}",
            "-F", f"number={number}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    issue = json.loads(result.stdout)["data"]["repository"]["issue"]

    _write("number", str(issue["number"]))
    _write("title", issue["title"])
    _write("labels", ", ".join(n["name"] for n in issue["labels"]["nodes"]))
    _write("body", issue["body"] or "", multiline=True)

    raw_comments = [
        c for c in issue["comments"]["nodes"]
        if c["author"]["login"] != "github-actions"
    ]
    if raw_comments:
        parts = [
            f"### Comment by {c['author']['login']} ({c['createdAt']})\n{c['body']}"
            for c in raw_comments
        ]
        comments_text = (
            "COMMENTS (from the owner, chronological, excluding this pipeline's own"
            " comments — treat these as clarifications or amendments to the issue above):\n"
            + "\n\n---\n\n".join(parts)
        )
        _write("comments", comments_text, multiline=True)
    else:
        _write("comments", "", multiline=True)


if __name__ == "__main__":
    main()
