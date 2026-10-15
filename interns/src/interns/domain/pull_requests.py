"""Pull request read model: the description and the latest human comments."""

from __future__ import annotations

from dataclasses import dataclass

from .. import gh
from .issues import PIPELINE_AUTHOR, Comment

MAX_COMMENTS = 5


@dataclass
class PullRequest:
    number: int
    title: str
    body: str
    total_comments: int
    comments: list[Comment]


def fetch_pull_request(repo: str, number: int) -> PullRequest:
    raw = gh.pr_view(repo, number, ["number", "title", "body", "comments"])
    human = [
        Comment(author=(c["author"] or {}).get("login", "ghost"), created_at=c["createdAt"], body=c["body"])
        for c in raw["comments"]
        if (c["author"] or {}).get("login") != PIPELINE_AUTHOR
    ]
    return PullRequest(
        number=raw["number"],
        title=raw["title"],
        body=raw["body"] or "",
        total_comments=len(human),
        comments=human[-MAX_COMMENTS:],
    )
