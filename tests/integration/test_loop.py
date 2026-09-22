"""The coder -> reviewer loop's decision points, end to end.

Each test runs real entrypoints against fake `gh`/`git` and asserts on the
commands issued, the labels they leave behind and the step outputs.
"""

import json

import pytest

from testkit.harness import REPO, Scenario, labels_payload

ISSUE = "7"
PR = "12"
HEAD = "sha-head"
RUN_URL = f"https://github.example/{REPO}/actions/runs/4242"


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def review(state: str, commit: str = HEAD, login: str = "reviewer-bot") -> dict:
    return {"id": 1, "user": {"login": login}, "state": state, "commit_id": commit}


def reviews_on_pr(scenario: Scenario, *reviews: dict) -> None:
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[list(reviews)])
    scenario.gh("pr", "view", "headRefOid", stdout={"headRefOid": HEAD})


def test_coder_success_squashes_pushes_opens_pr_and_reports_cost(scenario):
    scenario.gh("api", f"repos/{REPO}", stdout={"default_branch": "main"})
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="issue-7\n")
    scenario.git("rev-parse", "HEAD", stdout="tip-sha\n")
    scenario.git("merge-base", stdout="base-sha\n")
    scenario.git("log", stdout="feat: add thing\n")
    scenario.git("diff-tree", stdout="src/thing.py\n")
    scenario.gh("pr", "create", stdout=f"https://github.example/{REPO}/pull/{PR}\n")
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:coding"))
    exec_file = scenario.dir / "execution.json"
    exec_file.write_text(json.dumps([{"type": "result", "total_cost_usd": 0.1234}]))

    pushed = scenario.run_tool("push_branch")
    opened = scenario.run_tool("open_pr", issue_number=int(ISSUE), title="feat: add thing",
                               body="Adds the thing to the widget.")
    reported = scenario.run("pipeline.entrypoint", "report-run",
                            "--phase", "Coder", "--exec-file", str(exec_file), "--issue", ISSUE)
    handed_off = scenario.run("pipeline.entrypoint", "handoff-to-review", "--issue", ISSUE, "--pr", PR)

    assert [r.returncode for r in (pushed, opened, reported, handed_off)] == [0, 0, 0, 0]
    assert scenario.calls("git", "reset") == [["reset", "--soft", "base-sha"]]
    assert scenario.calls("git", "commit") == [["commit", "--quiet", "-m", "feat: add thing"]]
    assert scenario.calls("git", "push") == [["push", "--force-with-lease", "-u", "origin", "issue-7"]]
    (create,) = scenario.calls("gh", "pr", "create")
    assert create[create.index("--head") + 1] == "issue-7"
    assert create[create.index("--base") + 1] == "main"
    assert create[create.index("--body") + 1].endswith(f"Closes #{ISSUE}")
    assert scenario.comments("issue") == [(ISSUE, f"Coder [pipeline run]({RUN_URL}) — cost: $0.1234")]
    assert scenario.label_edits("pr") == [(PR, {"pr:in-review"}, {"pr:coding"})]


def test_coder_leaving_no_pr_flags_the_issue(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:in-progress"))

    result = scenario.run("pipeline.entrypoint", "handoff-to-review", "--issue", ISSUE)

    assert result.returncode == 0
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, {"status:in-progress"})]
    assert "without leaving an open PR" in scenario.comments("issue")[0][1]


def test_reviewer_approval_clears_the_pr_label(scenario):
    reviews_on_pr(scenario, review("APPROVED"))
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:in-review"))

    result = scenario.run("pipeline.entrypoint", "apply-verdict", "--pr", PR, "--issue", ISSUE)

    assert result.returncode == 0
    assert scenario.label_edits("pr") == [(PR, set(), {"pr:in-review"})]
    (number, body), = scenario.comments("issue")
    assert number == ISSUE and "Reviewer approved" in body
    assert scenario.calls("gh", "workflow") == []


def test_first_change_request_dispatches_a_fix_round(scenario):
    reviews_on_pr(scenario, review("CHANGES_REQUESTED"))
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:in-review"))

    result = scenario.run("pipeline.entrypoint", "apply-verdict", "--pr", PR, "--issue", ISSUE)

    assert result.returncode == 0
    assert scenario.label_edits("pr") == [(PR, {"pr:coding"}, {"pr:in-review"})]
    (dispatch,) = scenario.calls("gh", "workflow", "run")
    assert dispatch[:3] == ["workflow", "run", "code-pipeline.yml"]
    assert {"phase=coder", f"issue_number={ISSUE}", "fix_round=true"} <= set(dispatch)


def test_change_request_past_the_cap_escalates_to_a_human(scenario):
    reviews_on_pr(scenario, review("CHANGES_REQUESTED", commit="sha-old"), review("CHANGES_REQUESTED"))
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:in-review"))
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:in-progress"))

    result = scenario.run("pipeline.entrypoint", "apply-verdict", "--pr", PR, "--issue", ISSUE)

    assert result.returncode == 0
    assert scenario.calls("gh", "workflow") == []
    assert scenario.label_edits("pr") == [(PR, {"pr:needs-attention"}, {"pr:in-review"})]
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, {"status:in-progress"})]
    assert "Escalating to a human" in scenario.comments("pr")[0][1]


def test_red_check_routes_to_a_human_without_running_the_reviewer(scenario):
    scenario.gh("pr", "checks", code=1,
                stdout=[{"name": "ci", "bucket": "fail", "link": "https://github.example/runs/1/job/2"}])
    scenario.gh("pr", "view", "labels", stdout=labels_payload("pr:coding"))
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:in-progress"))
    no_config = {"INTERNS_CONFIG": str(scenario.workspace / "absent.yml")}

    gate = scenario.run("pipeline.entrypoint", "wait-for-checks", "--pr", PR, env=no_config)
    assert gate.outputs == {"ok": "false", "reason": "red checks: ci=fail"}

    routed = scenario.run("pipeline.entrypoint", "route-red-checks",
                          "--pr", PR, "--issue", ISSUE, "--reason", gate.outputs["reason"])

    assert routed.returncode == 0
    assert scenario.label_edits("pr") == [(PR, {"pr:needs-attention"}, {"pr:coding"})]
    assert scenario.label_edits("issue") == [(ISSUE, {"status:needs-attention"}, {"status:in-progress"})]
    assert "red checks: ci=fail" in scenario.comments("pr")[0][1]
    assert scenario.calls("gh", "api") == []


def test_issue_moves_through_refine_estimate_and_needs_attention(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:needs-refinement"))
    refined = scenario.run_tool("apply_refinement_outcome", issue_number=int(ISSUE),
                                outcome="refined", type_label="type:coding-task")
    assert refined.returncode == 0
    assert scenario.label_edits("issue") == [
        (ISSUE, {"status:refined", "type:coding-task"}, {"status:needs-refinement"}),
    ]

    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:refined", "type:coding-task"))
    estimated = scenario.run_tool("apply_estimation_outcome", issue_number=int(ISSUE), outcome="estimated",
                                  blast_radius="Low", touch="Low", human_involvement="Low", review_overhead="Low")
    assert estimated.returncode == 0
    assert scenario.label_edits("issue")[1] == (ISSUE, {"status:estimated", "size:XS"}, {"status:refined"})

    stalled = scenario.run_tool("apply_estimation_outcome", issue_number=int(ISSUE), outcome="needs-attention")
    assert stalled.returncode == 0
    assert scenario.label_edits("issue")[2] == (ISSUE, {"status:needs-attention"}, {"status:refined"})
