# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.0.0"]
# ///

import os
import subprocess

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("gh-issues")

_REPO = os.environ.get("GITHUB_REPOSITORY", "")


@mcp.tool()
def list_issues(label: str = "") -> str:
    """List open issues in the repository.

    Returns JSON: number, title, labels, state for each issue.
    Pass label to filter to a specific label (e.g. "status:needs-refinement").
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


@mcp.tool()
def view_issue(issue_number: int) -> str:
    """Get full details of a single issue: number, title, body, labels, state, comments."""
    result = subprocess.run(
        [
            "gh", "issue", "view", str(issue_number),
            "--repo", _REPO,
            "--json", "number,title,body,labels,state,comments",
        ],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


if __name__ == "__main__":
    mcp.run()
