# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.0.0"]
# ///

import json
import os
import pathlib
import subprocess
from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("gh-issues")

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


@mcp.tool()
def view_issue(
    issue_number: Annotated[int, Field(description="Issue number to fetch.")],
) -> str:
    """Get full details of one issue: number, title, body, labels, state, comments,
    and GitHub relationships (parent, sub-issues, blockedBy, blocking)."""
    owner, repo = _REPO.split("/", 1)
    result = subprocess.run(
        [
            "gh", "api", "graphql",
            "-f", f"query={_VIEW_QUERY}",
            "-F", f"owner={owner}",
            "-F", f"repo={repo}",
            "-F", f"number={issue_number}",
        ],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


if __name__ == "__main__":
    mcp.run()
