"""The plan job's commands, end to end: the event on disk in, the routed job out, plus the label/comment side
effects of a gate rejecting a run."""

import json

import pytest

from testkit import events
from testkit.harness import REPO, Result, Scenario, labels_payload

ISSUE = "7"
PR = "12"
HEAD = "sha-head"
CODER_BOT = "interns-coder[bot]"
CODE = "coder,reviewer,pr_closed"
ISSUES = "refine,estimate"
GREEN = [{"name": "ci", "bucket": "pass", "link": "https://github.example/runs/1/job/2"}]
RED = [{"name": "ci", "bucket": "fail", "link": "https://github.example/runs/1/job/2"}]


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def run(scenario: Scenario, command: str, event: str, payload: dict, handles: str = CODE,
        env: dict[str, str] | None = None) -> Result:
    path = scenario.dir / "event.json"
    path.write_text(json.dumps(payload))
    return scenario.run(
        "interns.entrypoint", command, "--handles", handles,
        env={"GITHUB_EVENT_NAME": event, "GITHUB_EVENT_PATH": str(path), **(env or {})},
    )


def routed(job: str, *, issue: str = "", pr: str = "", fix_round: str = "false", skip_reason: str = "") -> dict:
    return {"job": job, "issue": issue, "pr": pr, "fix_round": fix_round, "skip_reason": skip_reason}


def review(commit: str = "sha-old", login: str = "reviewer-bot") -> dict:
    return {"id": 1, "user": {"login": login}, "state": "CHANGES_REQUESTED", "commit_id": commit,
            "submitted_at": "2026-01-01T00:00:00Z", "body": ""}


def pr_state(scenario: Scenario, *reviews: dict, checks: list = GREEN) -> None:
    scenario.gh("pr", "checks", stdout=checks)
    scenario.gh("pr", "view", "headRefOid", stdout={"headRefOid": HEAD})
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[list(reviews)])
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:in-review"))


def confirm_review(scenario: Scenario, payload: dict, event: str = "pull_request", max_reviews: int | None = None):
    config = scenario.workspace / "interns.yml"
    if max_reviews is not None:
        config.write_text(f"review_loop:\n  max_automatic_reviews: {max_reviews}\n")
    return run(scenario, "confirm-route", event, payload, env={"INTERNS_CONFIG": str(config), "CODER_BOT": CODER_BOT})


def test_route_event_maps_a_label_to_its_job_without_calling_gh(scenario):
    result = run(scenario, "route-event", "issues", events.issues_labeled(7, "status:ready"))

    assert result.outputs == routed("coder", issue=ISSUE)
    assert scenario.calls("gh") == []


def test_route_event_reports_why_nothing_runs(scenario):
    result = run(scenario, "route-event", "pull_request", events.pull_request(draft=True))

    assert result.outputs["job"] == "none"
    assert "draft" in result.outputs["skip_reason"]


def test_route_event_leaves_the_other_workflows_jobs_alone(scenario):
    result = run(scenario, "route-event", "issues", events.issues_labeled(7, "status:ready"), handles=ISSUES)

    assert result.outputs["job"] == "none"
    assert "other workflow" in result.outputs["skip_reason"]


def test_route_event_fails_on_an_unsupported_event(scenario):
    result = run(scenario, "route-event", "push", {})

    assert result.returncode != 0
    assert "unsupported event" in result.stderr


def test_route_event_fails_on_an_unknown_dispatch_phase(scenario):
    result = run(scenario, "route-event", "workflow_dispatch", events.dispatch(phase="deploy"))

    assert result.returncode != 0
    assert "unknown dispatch phase" in result.stderr


def test_pr_closed_needs_no_lookup(scenario):
    result = run(scenario, "confirm-route", "pull_request", events.pull_request("closed"))

    assert result.outputs == routed("pr_closed", pr=PR)
    assert scenario.calls("gh") == []


def test_refine_label_runs_the_refiner_without_a_gate(scenario):
    result = run(scenario, "confirm-route", "issues", events.issues_labeled(7, "status:needs-refinement"), handles=ISSUES)

    assert result.outputs == routed("refine", issue=ISSUE)
    assert scenario.calls("gh") == []


def test_ready_issue_of_an_implementable_type_runs_the_coder(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:bug", "status:ready"))

    result = run(scenario, "confirm-route", "issues", events.issues_labeled(7, "status:ready"))

    assert result.outputs == routed("coder", issue=ISSUE)
    assert scenario.label_edits("issue") == []


def test_stale_trigger_on_an_in_progress_issue_runs_nothing(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:bug", "status:in-progress"))

    result = run(scenario, "confirm-route", "issues", events.issues_labeled(7, "status:ready"))

    assert result.outputs["job"] == "none"
    assert "stale or duplicate trigger" in result.outputs["skip_reason"]
    assert scenario.label_edits("issue") == []


def test_stale_trigger_on_a_needs_attention_issue_runs_nothing(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:bug", "status:needs-attention"))

    result = run(scenario, "confirm-route", "issues", events.issues_labeled(7, "status:ready"))

    assert result.outputs["job"] == "none"


def test_fix_round_dispatch_runs_against_an_in_progress_issue_without_any_lookup(scenario):
    result = run(scenario, "confirm-route", "workflow_dispatch",
                 events.dispatch(phase="coder", issue_number="7", fix_round="true"))

    assert result.outputs == routed("coder", issue=ISSUE, fix_round="true")
    assert scenario.calls("gh") == []


def test_unimplementable_issue_type_is_parked_and_runs_nothing(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:spike", "status:ready"))

    result = run(scenario, "confirm-route", "issues", events.issues_labeled(7, "status:ready"))

    assert result.outputs["job"] == "none"
    assert result.outputs["issue"] == ISSUE
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, {"status:ready"})]
    assert "only those two types are implementable" in scenario.comments("issue")[0][1]


def test_estimable_issue_type_runs_the_estimator(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:spike", "status:refined"))

    result = run(scenario, "confirm-route", "issues", events.issues_labeled(7, "status:refined"), handles=ISSUES)

    assert result.outputs == routed("estimate", issue=ISSUE)
    assert scenario.label_edits("issue") == []


def test_epic_is_parked_instead_of_estimated(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:epic", "status:refined"))

    result = run(scenario, "confirm-route", "issues", events.issues_labeled(7, "status:refined"), handles=ISSUES)

    assert result.outputs["job"] == "none"
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, {"status:refined"})]
    assert "Epics aren't sized directly" in scenario.comments("issue")[0][1]


def test_green_unreviewed_pr_is_reviewed(scenario):
    pr_state(scenario)

    result = confirm_review(scenario, events.pull_request())

    assert result.outputs == routed("reviewer", pr=PR)
    assert scenario.calls("gh", "pr", "edit") == []


def test_red_check_routes_to_a_human_without_running_the_reviewer(scenario):
    pr_state(scenario, checks=RED)

    result = confirm_review(scenario, events.pull_request())

    assert result.outputs["job"] == "none"
    assert "red checks: ci=fail" in result.outputs["skip_reason"]
    assert scenario.label_edits("pr") == [(PR, {"pr:needs-attention"}, {"pr:in-review"})]
    assert scenario.label_edits("issue") == []
    assert "red checks: ci=fail" in scenario.comments("pr")[0][1]


def test_a_bot_pr_that_is_not_the_coders_is_skipped(scenario):
    pr_state(scenario)

    result = confirm_review(scenario, events.pull_request(login="dependabot[bot]", user_type="Bot"))

    assert result.outputs["job"] == "none"
    assert "not a pipeline PR" in result.outputs["skip_reason"]
    assert scenario.calls("gh", "api") == []


def test_the_coders_own_bot_pr_is_reviewed(scenario):
    pr_state(scenario)

    result = confirm_review(scenario, events.pull_request(login=CODER_BOT, user_type="Bot"))

    assert result.outputs["job"] == "reviewer"


def test_a_head_that_already_has_a_review_is_a_duplicate(scenario):
    pr_state(scenario, review(commit=HEAD))

    result = confirm_review(scenario, events.pull_request())

    assert result.outputs["job"] == "none"
    assert "duplicate event" in result.outputs["skip_reason"]
    assert scenario.calls("gh", "pr", "edit") == []


def test_an_earlier_commit_review_does_not_make_the_head_a_duplicate(scenario):
    pr_state(scenario, review(commit="sha-old"))

    assert confirm_review(scenario, events.pull_request()).outputs["job"] == "reviewer"


def test_a_pr_at_the_review_cap_is_escalated_instead_of_reviewed(scenario):
    pr_state(scenario, review(commit="sha-1"), review(commit="sha-2"))

    result = confirm_review(scenario, events.pull_request(), max_reviews=2)

    assert result.outputs["job"] == "none"
    assert result.outputs["skip_reason"] == "automatic review cap reached"
    assert scenario.label_edits("pr") == [(PR, {"pr:needs-attention"}, {"pr:in-review"})]
    (number, body), = scenario.comments("pr")
    assert number == PR and "Automatic review limit (2) reached" in body


def test_manual_dispatch_skips_the_check_gate_and_the_cap(scenario):
    pr_state(scenario, review(commit="sha-1"), review(commit="sha-2"), checks=RED)

    result = confirm_review(scenario, events.dispatch(phase="reviewer", pr_number=PR),
                            event="workflow_dispatch", max_reviews=2)

    assert result.outputs == routed("reviewer", pr=PR)
    assert scenario.calls("gh", "pr", "checks") == []
    assert scenario.calls("gh", "pr", "edit") == []


def test_manual_dispatch_still_skips_an_already_reviewed_head(scenario):
    pr_state(scenario, review(commit=HEAD))

    result = confirm_review(scenario, events.dispatch(phase="reviewer", pr_number=PR), event="workflow_dispatch")

    assert result.outputs["job"] == "none"
