"""Builds the coder fix-round prompt text from the PR's latest
CHANGES_REQUESTED review, its inline comments and any conversation posted
after it -- deliberately excluding earlier, already-addressed rounds.
"""

import pytest

from testkit.harness import REPO, Scenario

PR = "12"
ISSUE = "7"
HEAD_REF = "issue-7-fix"


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def review(id_: int, state: str, submitted_at: str, body: str = "") -> dict:
    return {"id": id_, "user": {"login": "reviewer-bot"}, "state": state, "commit_id": "sha",
            "submitted_at": submitted_at, "body": body}


def test_gathers_the_latest_review_its_comments_and_later_conversation(scenario):
    scenario.git("fetch", "origin", HEAD_REF)
    scenario.git("checkout", HEAD_REF)
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[
        review(1, "APPROVED", "2024-01-01T00:00:00Z"),
        review(2, "CHANGES_REQUESTED", "2024-01-02T00:00:00Z", "Please fix the edge case."),
    ]])
    scenario.gh(f"repos/{REPO}/pulls/{PR}/comments", stdout=[[
        {"pull_request_review_id": 2, "path": "src/thing.py", "line": 10,
         "body": "This branch is unreachable.", "created_at": "2024-01-02T00:01:00Z"},
        {"pull_request_review_id": 1, "path": "src/thing.py", "line": 5,
         "body": "old comment on an earlier review", "created_at": "2024-01-01T00:01:00Z"},
    ]])
    scenario.gh(f"repos/{REPO}/issues/{PR}/comments", stdout=[[
        {"user": {"login": "alice"}, "body": "Any update?", "created_at": "2024-01-02T02:00:00Z"},
        {"user": {"login": "bob"}, "body": "too early", "created_at": "2024-01-01T12:00:00Z"},
    ]])

    result = scenario.run("pipeline.entrypoint", "gather-fix-feedback",
                          "--pr", PR, "--head-ref", HEAD_REF, "--issue", ISSUE)

    assert result.returncode == 0
    text = result.outputs["text"]
    assert "Please fix the edge case." in text
    assert "src/thing.py:10\n  This branch is unreachable." in text
    assert "old comment on an earlier review" not in text  # belongs to the earlier, addressed review
    assert "### alice (2024-01-02T02:00:00Z)\nAny update?" in text
    assert "too early" not in text  # posted before the CHANGES_REQUESTED review
    assert scenario.calls("git", "checkout") == [["checkout", HEAD_REF]]


def test_no_summary_body_gets_a_placeholder(scenario):
    scenario.git("fetch", "origin", HEAD_REF)
    scenario.git("checkout", HEAD_REF)
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review(1, "CHANGES_REQUESTED", "2024-01-01T00:00:00Z")]])
    scenario.gh(f"repos/{REPO}/pulls/{PR}/comments", stdout=[[]])
    scenario.gh(f"repos/{REPO}/issues/{PR}/comments", stdout=[[]])

    result = scenario.run("pipeline.entrypoint", "gather-fix-feedback",
                          "--pr", PR, "--head-ref", HEAD_REF, "--issue", ISSUE)

    assert result.returncode == 0
    assert "(no summary body)" in result.outputs["text"]


def test_fails_when_the_pr_has_no_changes_requested_review(scenario):
    scenario.git("fetch", "origin", HEAD_REF)
    scenario.git("checkout", HEAD_REF)
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review(1, "APPROVED", "2024-01-01T00:00:00Z")]])

    result = scenario.run("pipeline.entrypoint", "gather-fix-feedback",
                          "--pr", PR, "--head-ref", HEAD_REF, "--issue", ISSUE)

    assert result.returncode == 1
    assert f"no CHANGES_REQUESTED review found for PR #{PR}" in result.stderr
    assert not any("comments" in call[-1] for call in scenario.calls("gh", "api"))


def test_fails_fast_when_the_dispatch_has_no_open_pr(scenario):
    result = scenario.run("pipeline.entrypoint", "gather-fix-feedback",
                          "--pr", "", "--head-ref", HEAD_REF, "--issue", ISSUE)

    assert result.returncode == 1
    assert f"no open PR for issue #{ISSUE}" in result.stderr
    assert scenario.calls("git") == []
