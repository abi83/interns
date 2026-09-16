# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==2.2.0"]
# ///

import json
import os
import pathlib
import subprocess
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

mcp = MCPServer("gh-issues")

_REPO = os.environ.get("GITHUB_REPOSITORY", "")

# labels.json lives two levels up from this file: .interns/.github/labels.json
_LABELS_JSON = pathlib.Path(__file__).parent.parent.parent / "labels.json"


def _load_label_names() -> list[str]:
    try:
        data = json.loads(_LABELS_JSON.read_text())
        return [entry["name"] for entry in data.get("labels", [])]
    except (OSError, KeyError, json.JSONDecodeError):
        return []


_KNOWN_LABELS = _load_label_names()
_LABEL_DESCRIPTION = (
    "Label to filter by. Pass '' (or omit) to list all open issues. "
    + (f"Valid labels: {', '.join(_KNOWN_LABELS)}." if _KNOWN_LABELS else "")
)


@mcp.tool()
def list_issues(
    label: Annotated[str, Field(description=_LABEL_DESCRIPTION)] = "",
) -> str:
    """List open issues in the repository.

    Returns a JSON array; each element has number, title, labels, state.
    """
    cmd = [
        "gh", "issue", "list",
        "--repo", _REPO,
        "--state", "open",
        "--json", "number,title,labels,state",
        "--limit", "100",
    ]
    if label:
        cmd += ["--label", label]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


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


def _fetch_issue(number: int) -> str:
    """Run the GraphQL query and return the raw response JSON string."""
    owner, repo = _REPO.split("/", 1)
    result = subprocess.run(
        [
            "gh", "api", "graphql",
            "-f", f"query={_VIEW_QUERY}",
            "-F", f"owner={owner}",
            "-F", f"repo={repo}",
            "-F", f"number={number}",
        ],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


@mcp.tool()
def view_issue(
    issue_number: Annotated[int, Field(description="Issue number to fetch.")],
) -> str:
    """Get full details of one issue: number, title, body, labels, state, comments,
    and GitHub relationships (parent, sub-issues, blockedBy, blocking)."""
    return _fetch_issue(issue_number)


def _write_github_output(issue: dict) -> None:
    """Write issue fields to $GITHUB_OUTPUT for use in workflow steps."""
    output_path = os.environ.get("GITHUB_OUTPUT", "")

    def write(key: str, value: str, multiline: bool = False) -> None:
        if not output_path:
            print(f"{key}={value!r}")
            return
        with open(output_path, "a") as f:
            if multiline:
                sentinel = f"EOF_{key.upper()}"
                f.write(f"{key}<<{sentinel}\n{value}\n{sentinel}\n")
            else:
                f.write(f"{key}={value}\n")

    write("number", str(issue["number"]))
    write("title", issue["title"])
    write("labels", ", ".join(n["name"] for n in issue["labels"]["nodes"]))
    write("body", issue["body"] or "", multiline=True)

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
        write("comments", comments_text, multiline=True)
    else:
        write("comments", "", multiline=True)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "--fetch":
        _raw = _fetch_issue(int(sys.argv[2]))
        _issue = json.loads(_raw)["data"]["repository"]["issue"]
        _write_github_output(_issue)
    else:
        mcp.run()
