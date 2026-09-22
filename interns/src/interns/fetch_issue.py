"""Fetches an issue (with comments and GitHub relationships) and writes its
fields to `$GITHUB_OUTPUT` for a workflow prompt. Also the shared read model
behind the MCP server's `view_issue` tool.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import cli, gh
from .ctx import ActionsCtx

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


@dataclass
class Comment:
    author: str
    created_at: str
    body: str


@dataclass
class RelatedIssue:
    number: int
    title: str
    state: str


@dataclass
class Issue:
    number: int
    title: str
    body: str
    state: str
    labels: list[str]
    comments: list[Comment]
    parent: RelatedIssue | None = None
    sub_issues: list[RelatedIssue] = field(default_factory=list)
    blocked_by: list[RelatedIssue] = field(default_factory=list)
    blocking: list[RelatedIssue] = field(default_factory=list)


def fetch_issue(repo: str, number: int) -> Issue:
    """Run the GraphQL query and parse the response into an Issue."""
    owner, name = repo.split("/", 1)
    raw = gh.graphql(_VIEW_QUERY, owner=owner, repo=name, number=number)["data"]["repository"]["issue"]
    return Issue(
        number=raw["number"],
        title=raw["title"],
        body=raw["body"] or "",
        state=raw["state"],
        labels=[n["name"] for n in raw["labels"]["nodes"]],
        comments=[
            Comment(author=c["author"]["login"], created_at=c["createdAt"], body=c["body"])
            for c in raw["comments"]["nodes"]
        ],
        parent=RelatedIssue(**raw["parent"]) if raw.get("parent") else None,
        sub_issues=[RelatedIssue(**n) for n in raw["subIssues"]["nodes"]],
        blocked_by=[RelatedIssue(**n) for n in raw["blockedBy"]["nodes"]],
        blocking=[RelatedIssue(**n) for n in raw["blocking"]["nodes"]],
    )


def write_github_output(issue: Issue) -> None:
    """Write issue fields to $GITHUB_OUTPUT for use in workflow steps."""
    output_path = os.environ.get("GITHUB_OUTPUT", "")

    def write(key: str, value: str, multiline: bool = False) -> None:
        if not output_path:
            print(f"{key}={value!r}")
            return
        entry = cli.github_output_block(key, value.encode()) if multiline else f"{key}={value}\n".encode()
        cli.append_output(entry)

    write("number", str(issue.number))
    write("title", issue.title)
    write("labels", ", ".join(issue.labels))
    write("body", issue.body, multiline=True)

    human_comments = [c for c in issue.comments if c.author != "github-actions"]
    if human_comments:
        parts = [
            f"### Comment by {c.author} ({c.created_at})\n{c.body}"
            for c in human_comments
        ]
        comments_text = (
            "COMMENTS (from the owner, chronological, excluding this pipeline's own"
            " comments — treat these as clarifications or amendments to the issue above):\n"
            + "\n\n---\n\n".join(parts)
        )
        write("comments", comments_text, multiline=True)
    else:
        write("comments", "", multiline=True)


def _main(ctx: ActionsCtx, argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="interns.entrypoint fetch-issue")
    parser.add_argument("--issue", type=int, required=True)
    args = parser.parse_args(argv)
    write_github_output(fetch_issue(ctx.repo, args.issue))
    return 0
