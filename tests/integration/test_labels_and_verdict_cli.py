"""Direct CLI entrypoints for `pipeline.labels` and `pipeline.verdict`:
workflow steps call these subcommands straight from YAML via `pipeline.entrypoint`.
"""

import pytest

from testkit.harness import REPO, Scenario, labels_payload

PR = "12"
ISSUE = "7"
HEAD = "sha-head"


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def review(state: str, commit: str = HEAD, login: str = "reviewer-bot") -> dict:
    return {"id": 1, "user": {"login": login}, "state": state, "commit_id": commit}


# --- pipeline.labels ---------------------------------------------------------

def test_labels_issue_labels_prints_a_comma_joined_list(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:ready", "type:bug"))

    result = scenario.run("pipeline.entrypoint", "labels", "issue-labels", ISSUE)

    assert result.returncode == 0
    assert result.stdout.strip() == "status:ready,type:bug"


def test_labels_pr_labels_prints_a_comma_joined_list(scenario):
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:coding"))

    result = scenario.run("pipeline.entrypoint", "labels", "pr-labels", PR)

    assert result.returncode == 0
    assert result.stdout.strip() == "pr:coding"


def test_labels_set_issue_status_moves_between_statuses(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:in-progress"))

    result = scenario.run("pipeline.entrypoint", "labels", "set-issue-status", ISSUE, "status:ready")

    assert result.returncode == 0
    assert scenario.label_edits("issue") == [(ISSUE, {"status:ready"}, {"status:in-progress"})]


def test_labels_edit_issue_labels_only_changes_what_is_missing(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:bug"))

    result = scenario.run("pipeline.entrypoint", "labels", "edit-issue-labels", ISSUE,
                          "--add", "type:bug", "--add", "status:ready")

    assert result.returncode == 0
    assert scenario.label_edits("issue") == [(ISSUE, {"status:ready"}, set())]


def test_labels_set_pr_label_switches_the_pipeline_label(scenario):
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:coding"))

    result = scenario.run("pipeline.entrypoint", "labels", "set-pr-label", PR, "pr:in-review")

    assert result.returncode == 0
    assert scenario.label_edits("pr") == [(PR, {"pr:in-review"}, {"pr:coding"})]


def test_labels_set_pr_label_with_no_target_clears_all_pipeline_labels(scenario):
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:in-review"))

    result = scenario.run("pipeline.entrypoint", "labels", "set-pr-label", PR)

    assert result.returncode == 0
    assert scenario.label_edits("pr") == [(PR, set(), {"pr:in-review"})]


def test_labels_escalate_pr_sets_needs_attention(scenario):
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:coding"))

    result = scenario.run("pipeline.entrypoint", "labels", "escalate-pr", PR)

    assert result.returncode == 0
    assert scenario.label_edits("pr") == [(PR, {"pr:needs-attention"}, {"pr:coding"})]


# --- pipeline.verdict ---------------------------------------------------------

def test_verdict_verdict_for_head_prints_the_latest_state(scenario):
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review("APPROVED")]])

    result = scenario.run("pipeline.entrypoint", "verdict", "--pr", PR, "verdict-for-head", HEAD)

    assert result.returncode == 0
    assert result.stdout.strip() == "APPROVED"


def test_verdict_verdict_for_head_is_empty_for_a_stale_review(scenario):
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review("APPROVED", commit="old-sha")]])

    result = scenario.run("pipeline.entrypoint", "verdict", "--pr", PR, "verdict-for-head", HEAD)

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_verdict_rounds_requested_excludes_the_given_commit(scenario):
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[
        review("CHANGES_REQUESTED", commit="old-sha"),
        review("CHANGES_REQUESTED", commit=HEAD),
    ]])

    result = scenario.run("pipeline.entrypoint", "verdict", "--pr", PR,
                          "rounds-requested", "--exclude-commit", HEAD)

    assert result.returncode == 0
    assert result.stdout.strip() == "1"


def test_verdict_review_count_only_counts_the_given_login(scenario):
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[
        review("APPROVED", login="reviewer-bot"),
        review("COMMENTED", login="a-human"),
    ]])

    result = scenario.run("pipeline.entrypoint", "verdict", "--pr", PR, "review-count")

    assert result.returncode == 0
    assert result.stdout.strip() == "1"


def test_verdict_summary_for_head_prints_both_verdict_and_count_from_one_fetch(scenario):
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review("CHANGES_REQUESTED")]])

    result = scenario.run("pipeline.entrypoint", "verdict", "--pr", PR, "summary-for-head", HEAD)

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["verdict=CHANGES_REQUESTED", "count=1"]
