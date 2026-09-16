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


@mcp.tool()
def view_issue(
    issue_number: Annotated[int, Field(description="Issue number to fetch.")],
) -> str:
    """Get full details of one issue: number, title, body, labels, state, and comments."""
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
