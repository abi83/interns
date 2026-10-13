"""The plan job's decisions, end to end: which jobs run, and the label/comment side effects of skipping them."""

import pytest

from testkit.harness import REPO, Scenario, labels_payload

ISSUE = "7"
PR = "12"
HEAD = "sha-head"
CODER_BOT = "interns-coder[bot]"
GREEN = [{"name": "ci", "bucket": "pass", "link": "https://github.example/runs/1/job/2"}]
RED = [{"name": "ci", "bucket": "fail", "link": "https://github.example/runs/1/job/2"}]


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def review(commit: str = "sha-old", login: str = "reviewer-bot") -> dict:
    return {"id": 1, "user": {"login": login}, "state": "CHANGES_REQUESTED", "commit_id": commit,
            "submitted_at": "2026-01-01T00:00:00Z", "body": ""}


def pr_state(scenario: Scenario, *reviews: dict, checks: list = GREEN) -> None:
    scenario.gh("pr", "checks", stdout=checks)
    scenario.gh("pr", "view", "headRefOid", stdout={"headRefOid": HEAD})
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[list(reviews)])
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:in-review"))


def plan_review(scenario: Scenario, *, event: str = "pull_request", author: tuple[str, str] = ("alice", "User"),
                max_reviews: int | None = None):
    config = scenario.workspace / "interns.yml"
    if max_reviews is not None:
        config.write_text(f"review_loop:\n  max_automatic_reviews: {max_reviews}\n")
    env = {"GITHUB_EVENT_NAME": event, "INTERNS_CONFIG": str(config)}
    return scenario.run("interns.entrypoint", "plan-review", "--pr", PR, "--coder-bot", CODER_BOT,
                        "--pr-author-login", author[0], "--pr-author-type", author[1], env=env)


def test_green_unreviewed_pr_is_reviewed(scenario):
    pr_state(scenario)

    result = plan_review(scenario)

    assert result.outputs == {"run_review": "true"}
    assert scenario.calls("gh", "pr", "edit") == []


def test_red_check_routes_to_a_human_without_running_the_reviewer(scenario):
    pr_state(scenario, checks=RED)

    result = plan_review(scenario)

    assert result.outputs == {"run_review": "false"}
    assert scenario.label_edits("pr") == [(PR, {"pr:needs-attention"}, {"pr:in-review"})]
    assert scenario.label_edits("issue") == []
    assert "red checks: ci=fail" in scenario.comments("pr")[0][1]


def test_a_bot_pr_that_is_not_the_coders_is_skipped(scenario):
    pr_state(scenario)

    result = plan_review(scenario, author=("dependabot[bot]", "Bot"))

    assert result.outputs == {"run_review": "false"}
    assert scenario.calls("gh", "api") == []


def test_the_coders_own_bot_pr_is_reviewed(scenario):
    pr_state(scenario)

    assert plan_review(scenario, author=(CODER_BOT, "Bot")).outputs == {"run_review": "true"}


def test_a_head_that_already_has_a_review_is_a_duplicate(scenario):
    pr_state(scenario, review(commit=HEAD))

    result = plan_review(scenario)

    assert result.outputs == {"run_review": "false"}
    assert scenario.calls("gh", "pr", "edit") == []


def test_an_earlier_commit_review_does_not_make_the_head_a_duplicate(scenario):
    pr_state(scenario, review(commit="sha-old"))

    assert plan_review(scenario).outputs == {"run_review": "true"}


def test_a_pr_at_the_review_cap_is_escalated_instead_of_reviewed(scenario):
    pr_state(scenario, review(commit="sha-1"), review(commit="sha-2"))

    result = plan_review(scenario, max_reviews=2)

    assert result.outputs == {"run_review": "false"}
    assert scenario.label_edits("pr") == [(PR, {"pr:needs-attention"}, {"pr:in-review"})]
    (number, body), = scenario.comments("pr")
    assert number == PR and "Automatic review limit (2) reached" in body


def test_manual_dispatch_skips_the_check_gate_and_the_cap(scenario):
    pr_state(scenario, review(commit="sha-1"), review(commit="sha-2"), checks=RED)

    result = plan_review(scenario, event="workflow_dispatch", author=("", ""), max_reviews=2)

    assert result.outputs == {"run_review": "true"}
    assert scenario.calls("gh", "pr", "checks") == []
    assert scenario.calls("gh", "pr", "edit") == []


def test_manual_dispatch_still_skips_an_already_reviewed_head(scenario):
    pr_state(scenario, review(commit=HEAD))

    result = plan_review(scenario, event="workflow_dispatch", author=("", ""))

    assert result.outputs == {"run_review": "false"}


def plan_coder(scenario: Scenario, *, fix_round: str = "false"):
    return scenario.run("interns.entrypoint", "plan-coder-run", "--issue", ISSUE, "--fix-round", fix_round)


def test_ready_issue_of_an_implementable_type_runs_the_coder(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:bug", "status:ready"))

    result = plan_coder(scenario)

    assert result.outputs == {"skip": "false", "fix_round": "false"}
    assert scenario.label_edits("issue") == []


def test_stale_trigger_on_an_in_progress_issue_is_skipped(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:bug", "status:in-progress"))

    assert plan_coder(scenario).outputs == {"skip": "true", "fix_round": "false"}
    assert scenario.label_edits("issue") == []


def test_stale_trigger_on_a_needs_attention_issue_is_skipped(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:bug", "status:needs-attention"))

    assert plan_coder(scenario).outputs == {"skip": "true", "fix_round": "false"}


def test_fix_round_runs_against_an_in_progress_issue_without_any_lookup(scenario):
    result = plan_coder(scenario, fix_round="true")

    assert result.outputs == {"skip": "false", "fix_round": "true"}
    assert scenario.calls("gh") == []


def test_unimplementable_issue_type_is_parked_and_skipped(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:spike", "status:ready"))

    result = plan_coder(scenario)

    assert result.outputs == {"skip": "true", "fix_round": "false"}
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, {"status:ready"})]
    assert "only those two types are implementable" in scenario.comments("issue")[0][1]


def test_estimable_issue_type_runs_the_estimator(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:spike", "status:refined"))

    result = scenario.run("interns.entrypoint", "plan-estimate-run", "--issue", ISSUE)

    assert result.outputs == {"skip": "false"}
    assert scenario.label_edits("issue") == []


def test_epic_is_parked_instead_of_estimated(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:epic", "status:refined"))

    result = scenario.run("interns.entrypoint", "plan-estimate-run", "--issue", ISSUE)

    assert result.outputs == {"skip": "true"}
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, {"status:refined"})]
    assert "Epics aren't sized directly" in scenario.comments("issue")[0][1]
