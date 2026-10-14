"""GitHub event payloads in the shape the Actions runner writes to $GITHUB_EVENT_PATH.

Every payload is sent by `github-actions[bot]` unless `sender` says otherwise, an
identity the actor guard accepts without a permission lookup."""

from __future__ import annotations

PIPELINE_BOT = "github-actions[bot]"


def actor(login: str = PIPELINE_BOT, user_type: str | None = None) -> dict:
    return {"login": login, "type": user_type or ("Bot" if login.endswith("[bot]") else "User")}


def issues_labeled(issue: int, label: str, *, sender: str = PIPELINE_BOT) -> dict:
    return {"action": "labeled", "issue": {"number": issue}, "label": {"name": label}, "sender": actor(sender)}


def pull_request(
    action: str = "opened", number: int = 12, *, draft: bool = False, fork: bool = False,
    login: str = "alice", user_type: str = "User", sender: str = PIPELINE_BOT,
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
        "sender": actor(sender),
    }


def dispatch(*, sender: str = PIPELINE_BOT, **inputs: str) -> dict:
    return {"inputs": inputs, "sender": actor(sender)}


def workflow_run(
    head_sha: str = "sha-head", *, pr: int | None = 12, pr_head_sha: str | None = None, own: bool = False,
    sender: str = PIPELINE_BOT, run_actor: str = PIPELINE_BOT, triggering_actor: str = PIPELINE_BOT,
) -> dict:
    pull_requests = [] if pr is None else [{"number": pr, "head": {"sha": pr_head_sha or head_sha}}]
    return {
        "action": "completed",
        "workflow": {"id": 100},
        "workflow_run": {
            "head_sha": head_sha, "workflow_id": 100 if own else 200, "pull_requests": pull_requests,
            "actor": actor(run_actor), "triggering_actor": actor(triggering_actor),
        },
        "sender": actor(sender),
    }
