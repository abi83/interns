"""GitHub event payloads in the shape the Actions runner writes to $GITHUB_EVENT_PATH."""

from __future__ import annotations


def issues_labeled(issue: int, label: str) -> dict:
    return {"action": "labeled", "issue": {"number": issue}, "label": {"name": label}}


def pull_request(
    action: str = "opened", number: int = 12, *, draft: bool = False, fork: bool = False,
    login: str = "alice", user_type: str = "User",
) -> dict:
    return {
        "action": action,
        "number": number,
        "pull_request": {
            "number": number,
            "draft": draft,
            "head": {"repo": {"fork": fork}},
            "user": {"login": login, "type": user_type},
        },
    }


def dispatch(**inputs: str) -> dict:
    return {"inputs": inputs}
