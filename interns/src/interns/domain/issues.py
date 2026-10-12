"""Issue read model: an issue with its human comments and GitHub relationships."""

from __future__ import annotations

from dataclasses import dataclass, field

from .. import gh

PIPELINE_AUTHOR = "github-actions"


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
    raw = gh.issue_with_relations(repo, number)
    return Issue(
        number=raw["number"],
        title=raw["title"],
        body=raw["body"] or "",
        state=raw["state"],
        labels=[n["name"] for n in raw["labels"]["nodes"]],
        comments=[
            Comment(author=(c["author"] or {}).get("login", "ghost"), created_at=c["createdAt"], body=c["body"])
            for c in raw["comments"]["nodes"]
            if (c["author"] or {}).get("login") != PIPELINE_AUTHOR
        ],
        parent=RelatedIssue(**raw["parent"]) if raw.get("parent") else None,
        sub_issues=[RelatedIssue(**n) for n in raw["subIssues"]["nodes"]],
        blocked_by=[RelatedIssue(**n) for n in raw["blockedBy"]["nodes"]],
        blocking=[RelatedIssue(**n) for n in raw["blocking"]["nodes"]],
    )
