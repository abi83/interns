"""Pull request read model: the description, the latest human comments, and the diff."""

from __future__ import annotations

import re
from dataclasses import dataclass
from fnmatch import fnmatchcase

from .. import gh
from .issues import PIPELINE_AUTHOR, Comment

MAX_COMMENTS = 5
DIFF_LIMIT = 40_000
_FILE_HEADER = re.compile(r"^diff --git a/.+ b/(.+)$", re.MULTILINE)


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


def _split_by_file(diff: str) -> dict[str, str]:
    headers = list(_FILE_HEADER.finditer(diff))
    ends = [h.start() for h in headers[1:]] + [len(diff)]
    return {h.group(1): diff[h.start():end] for h, end in zip(headers, ends)}


def _changed_lines(section: str) -> tuple[int, int]:
    lines = section.splitlines()
    added = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
    return added, removed


def _overview(diff: str) -> str:
    rows = [f"{path} +{added} -{removed}" for path, section in _split_by_file(diff).items() for added, removed in [_changed_lines(section)]]
    header = (
        f"Diff is {len(diff)} characters, over the {DIFF_LIMIT} limit. Call again with `path`, "
        "a glob where * also matches /, to fetch part of it (e.g. 'src/components/*', 'tests/*', '*test*')."
    )
    return "\n".join([header, *rows])


def fetch_diff(repo: str, number: int, path: str | None) -> str:
    """The full diff when it fits; otherwise a per-file overview, to be narrowed with a `path` glob."""
    diff = gh.pr_diff(repo, number)
    if path is None:
        return diff if len(diff) <= DIFF_LIMIT else _overview(diff)
    selected = "".join(section for file, section in _split_by_file(diff).items() if fnmatchcase(file, path))
    if not selected:
        raise gh.InvalidInputError(f"No changed file in PR #{number} matches {path!r}")
    if len(selected) > DIFF_LIMIT:
        raise gh.InvalidInputError(
            f"{path!r} matches {len(selected)} characters, over the {DIFF_LIMIT} limit; narrow the pattern "
            "or read the file with Read"
        )
    return selected
