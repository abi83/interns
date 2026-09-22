"""Failure, hand-back and gating paths around the coder/reviewer loop, end to end.

Each test runs a real entrypoint against fake `gh` and asserts on the labels
and comments it leaves behind.
"""

import pytest

from testkit.harness import REPO, Scenario, labels_payload

ISSUE = "7"
PR = "12"
RUN_URL = f"https://github.example/{REPO}/actions/runs/4242"


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def test_estimated_spike_gets_the_advisory(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:spike", "status:estimated"))

    result = scenario.run("pipeline.entrypoint", "spike-advisory", "--issue", ISSUE)

    assert result.returncode == 0
    (number, body), = scenario.comments("issue")
    assert number == ISSUE and "This is a spike; no coder picks it up" in body


@pytest.mark.parametrize("current", [("type:coding-task", "status:estimated"), ("type:spike", "status:refined")])
def test_advisory_is_skipped_unless_an_estimated_spike(scenario, current):
    scenario.gh("issue", "view", "labels", stdout=labels_payload(*current))

    result = scenario.run("pipeline.entrypoint", "spike-advisory", "--issue", ISSUE)

    assert result.returncode == 0
    assert "no advisory" in result.stdout
    assert scenario.comments("issue") == []


def test_spike_advisory_does_not_swallow_a_gh_failure(scenario):
    scenario.gh("issue", "view", "labels", code=1, stderr="gh: rate limited")

    result = scenario.run("pipeline.entrypoint", "spike-advisory", "--issue", ISSUE)

    assert result.returncode != 0
    assert scenario.comments("issue") == []


def test_merged_pr_retires_the_issue_run_label(scenario):
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:in-review"))
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:in-progress"))

    result = scenario.run("pipeline.entrypoint", "handle-pr-closed",
                          "--pr", PR, "--issue", ISSUE, "--merged", "true")

    assert result.returncode == 0
    assert scenario.label_edits("pr") == [(PR, set(), {"pr:in-review"})]
    assert scenario.label_edits("issue") == [(ISSUE, set(), {"status:in-progress"})]
    assert scenario.comments("issue") == []


def test_pr_closed_unmerged_hands_the_issue_to_a_human(scenario):
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:in-review"))
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:in-progress"))

    result = scenario.run("pipeline.entrypoint", "handle-pr-closed",
                          "--pr", PR, "--issue", ISSUE, "--merged", "false")

    assert result.returncode == 0
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, {"status:in-progress"})]
    (number, body), = scenario.comments("issue")
    assert number == ISSUE and "closed without merging" in body and RUN_URL in body


def test_pr_closed_without_a_linked_issue_only_clears_the_pr_label(scenario):
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:in-review"))

    result = scenario.run("pipeline.entrypoint", "handle-pr-closed", "--pr", PR, "--merged", "false")

    assert result.returncode == 0
    assert scenario.label_edits("pr") == [(PR, set(), {"pr:in-review"})]
    assert scenario.calls("gh", "issue") == []


def test_coder_giving_up_escalates_instead_of_reaching_the_reviewer(scenario):
    (scenario.workspace / ".coder-gave-up.md").write_text("Needs a change under .github/workflows/.\n")
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:coding"))
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:in-progress"))

    result = scenario.run("pipeline.entrypoint", "handle-giveup", "--issue", ISSUE, "--pr", PR)

    assert result.outputs == {"gave_up": "true"}
    assert scenario.label_edits("pr") == [(PR, set(), {"pr:coding"})]
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, {"status:in-progress"})]
    (_, body), = scenario.comments("issue")
    assert "declined this task" in body and ".github/workflows/" in body and RUN_URL in body


def test_coder_giving_up_before_a_pr_exists_only_touches_the_issue(scenario):
    (scenario.workspace / ".coder-gave-up.md").write_text("Task is out of scope.\n")
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:in-progress"))

    result = scenario.run("pipeline.entrypoint", "handle-giveup", "--issue", ISSUE)

    assert result.outputs == {"gave_up": "true"}
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, {"status:in-progress"})]
    assert scenario.calls("gh", "pr") == []


def test_no_give_up_sentinel_leaves_everything_alone(scenario):
    result = scenario.run("pipeline.entrypoint", "handle-giveup", "--issue", ISSUE, "--pr", PR)

    assert result.outputs == {"gave_up": "false"}
    assert scenario.calls("gh") == []


def test_empty_give_up_sentinel_uses_a_placeholder_reason(scenario):
    (scenario.workspace / ".coder-gave-up.md").write_text("")
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:coding"))
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:in-progress"))

    result = scenario.run("pipeline.entrypoint", "handle-giveup", "--issue", ISSUE, "--pr", PR)

    assert result.outputs == {"gave_up": "true"}
    (_, body), = scenario.comments("issue")
    assert "_(no reason given)_" in body


def test_review_crash_flags_the_pr_and_the_issue(scenario):
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:in-review"))
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:in-progress"))

    result = scenario.run("pipeline.entrypoint", "flag-failure",
                          "--noun", "review", "--pr", PR, "--issue", ISSUE)

    assert result.returncode == 0
    assert scenario.label_edits("pr") == [(PR, {"pr:needs-attention"}, {"pr:in-review"})]
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, {"status:in-progress"})]
    assert scenario.comments("pr") == [(PR, f"Automated review failed. See the run: {RUN_URL}")]
    assert scenario.comments("issue") == []


def test_fix_round_crash_tells_the_issue_how_to_redispatch(scenario):
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:coding"))
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:in-progress"))

    result = scenario.run("pipeline.entrypoint", "flag-failure",
                          "--noun", "implementation", "--pr", PR, "--issue", ISSUE, "--fix-round")

    assert result.returncode == 0
    assert scenario.label_edits("pr") == [(PR, set(), {"pr:coding"})]
    assert scenario.comments("pr") == []
    (_, body), = scenario.comments("issue")
    assert f"gh workflow run code-pipeline.yml -f phase=coder -f issue_number={ISSUE} -f fix_round=true" in body


def test_estimation_crash_with_no_pr_comments_the_issue_directly(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:refined"))

    result = scenario.run("pipeline.entrypoint", "flag-failure", "--noun", "estimation", "--issue", ISSUE)

    assert result.returncode == 0
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, set())]
    assert scenario.comments("issue") == [(ISSUE, f"Automated estimation failed. See the run: {RUN_URL}")]
    assert scenario.calls("gh", "pr") == []


def test_flag_failure_with_no_target_fails(scenario):
    result = scenario.run("pipeline.entrypoint", "flag-failure", "--noun", "review")

    assert result.returncode != 0
    assert scenario.calls("gh") == []


def test_fix_round_failure_without_an_issue_fails_after_clearing_the_pr_label(scenario):
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:coding"))

    result = scenario.run("pipeline.entrypoint", "flag-failure",
                          "--noun", "implementation", "--pr", PR, "--fix-round")

    assert result.returncode != 0
    assert scenario.label_edits("pr") == [(PR, set(), {"pr:coding"})]
    assert scenario.comments("issue") == []
    assert scenario.comments("pr") == []


def test_accepted_issue_type_passes_the_gate(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:bug", "status:refined"))

    result = scenario.run("pipeline.entrypoint", "gate-issue-type",
                          "--issue", ISSUE, "--accepted", "type:coding-task,type:bug",
                          "--remove-status", "status:refined", "--reject-comment", "nope")

    assert result.outputs == {"skip": "false"}
    assert scenario.label_edits("issue") == []


def test_rejected_issue_type_is_parked_with_the_reason(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:epic", "status:refined"))

    result = scenario.run("pipeline.entrypoint", "gate-issue-type",
                          "--issue", ISSUE, "--accepted", "type:coding-task",
                          "--remove-status", "status:refined",
                          "--reject-comment", "Epics aren't sized directly.")

    assert result.outputs == {"skip": "true"}
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, {"status:refined"})]
    assert scenario.comments("issue") == [(ISSUE, "Epics aren't sized directly.")]


def test_original_issue_body_is_preserved_before_refinement(scenario):
    result = scenario.run("pipeline.entrypoint", "preserve-issue-body",
                          "--issue", ISSUE, env={"ISSUE_BODY": "original text"})

    assert result.returncode == 0
    (number, body), = scenario.comments("issue")
    assert number == ISSUE and "original text" in body and "<details>" in body
