"""The run-page Markdown summary, per phase, including its lookup-failure
paths: `gh` is rate-limited or the review list can't be fetched, and the
summary must still land (best-effort) with a plain fallback line rather
than crash the `if: always()` step that writes it.
"""

import json

import pytest

from testkit.harness import REPO, Scenario, labels_payload

ISSUE = "7"
PR = "12"
HEAD = "sha-head"


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def exec_file(scenario, **result_fields) -> str:
    path = scenario.dir / "execution.json"
    path.write_text(json.dumps([{"type": "result", **result_fields}]))
    return str(path)


def review(state: str, commit: str = HEAD, login: str = "reviewer-bot") -> dict:
    return {"id": 1, "user": {"login": login}, "state": state, "commit_id": commit}


def run_summary(scenario, *args: str) -> str:
    """Runs the entrypoint against a fresh $GITHUB_STEP_SUMMARY file and
    returns its contents. Asserts a clean exit -- this module never fails
    the calling step, so any non-zero return is itself a bug."""
    step_summary = scenario.dir / "summary.md"
    step_summary.write_text("")
    result = scenario.run("pipeline.run_summary", *args, env={"GITHUB_STEP_SUMMARY": str(step_summary)})
    assert result.returncode == 0, result.stderr
    return step_summary.read_text()


# --- Coder phase ---------------------------------------------------------

def test_coder_summary_reports_a_new_pr_and_cost(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh("pr", "diff", "--name-only", stdout="src/export.py\nsrc/export_test.py\n")
    ef = exec_file(scenario, total_cost_usd=0.42, num_turns=5, result="Opened the PR.")

    body = run_summary(scenario, "Coder", ef, "--issue", ISSUE, "--pr", PR)

    assert "## Coder run" in body
    assert "Add CSV export" in body
    assert f"PR opened — [#{PR}]" in body
    assert "**Files changed:** 2" in body
    assert "**Cost:** $0.42" in body and "5 turns" in body
    assert "Opened the PR." in body


def test_coder_summary_falls_back_when_the_issue_title_lookup_fails(scenario):
    scenario.gh("issue", "view", "title", code=1, stderr="gh: rate limited")
    scenario.gh("pr", "diff", "--name-only", stdout="src/export.py\n")
    ef = exec_file(scenario, total_cost_usd=0.1, result="Opened the PR.")

    body = run_summary(scenario, "Coder", ef, "--issue", ISSUE, "--pr", PR)

    issue_line = next(line for line in body.splitlines() if line.startswith("**Issue:**"))
    assert f"[#{ISSUE}]" in issue_line
    assert " — " not in issue_line  # no title suffix once the lookup fails


def test_coder_summary_with_no_pr_flags_the_missing_outcome(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    ef = exec_file(scenario, total_cost_usd=0.1, result="Ran out of turns.")

    body = run_summary(scenario, "Coder", ef, "--issue", ISSUE)

    assert "No PR — see the final message below." in body
    assert scenario.calls("gh", "pr") == []


def test_coder_fix_round_reports_an_updated_pr_when_the_head_moved(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review("CHANGES_REQUESTED", commit="old-sha")]])
    scenario.gh("pr", "view", "headRefOid", stdout={"headRefOid": "new-sha"})
    scenario.gh("pr", "diff", "--name-only", stdout="src/export.py\n")
    ef = exec_file(scenario, total_cost_usd=0.2, result="Pushed a fix.")

    body = run_summary(scenario, "Coder", ef, "--issue", ISSUE, "--pr", PR, "--round", "fix")

    assert "**Round:** Fix round 1" in body
    assert f"PR updated — [#{PR}]" in body


def test_coder_fix_round_flags_no_new_commit_when_the_head_did_not_move(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review("CHANGES_REQUESTED", commit="same-sha")]])
    scenario.gh("pr", "view", "headRefOid", stdout={"headRefOid": "same-sha"})
    scenario.gh("pr", "diff", "--name-only", stdout="")
    ef = exec_file(scenario, total_cost_usd=0.2, result=None)

    body = run_summary(scenario, "Coder", ef, "--issue", ISSUE, "--pr", PR, "--round", "fix")

    assert "No new commit pushed — see the final message below." in body


def test_coder_fix_round_state_falls_back_when_reviews_cannot_be_fetched(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", code=1, stderr="gh: rate limited")
    scenario.gh("pr", "view", "headRefOid", stdout={"headRefOid": "new-sha"})
    scenario.gh("pr", "diff", "--name-only", stdout="")
    ef = exec_file(scenario, total_cost_usd=0.2, result="Pushed a fix.")

    body = run_summary(scenario, "Coder", ef, "--issue", ISSUE, "--pr", PR, "--round", "fix")

    # No round number -- the fix-state fetch failed, so there's no fix_n to
    # report, and no last-flagged SHA to compare the (successfully fetched)
    # head against, so the outcome can't be "updated" either.
    assert "**Round:** Fix round\n" in body
    assert "No new commit pushed — see the final message below." in body


def test_coder_initial_round_reports_the_round_line(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh("pr", "diff", "--name-only", stdout="src/export.py\n")
    ef = exec_file(scenario, total_cost_usd=0.1, result="Opened the PR.")

    body = run_summary(scenario, "Coder", ef, "--issue", ISSUE, "--pr", PR, "--round", "initial")

    assert "**Round:** Initial implementation" in body


def test_coder_fix_round_falls_back_when_the_head_sha_lookup_fails(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review("CHANGES_REQUESTED", commit="old-sha")]])
    scenario.gh("pr", "view", "headRefOid", code=1, stderr="gh: rate limited")
    scenario.gh("pr", "diff", "--name-only", stdout="")
    ef = exec_file(scenario, total_cost_usd=0.2, result="Pushed a fix.")

    body = run_summary(scenario, "Coder", ef, "--issue", ISSUE, "--pr", PR, "--round", "fix")

    assert "**Round:** Fix round 1" in body
    assert "No new commit pushed — see the final message below." in body


def test_coder_summary_reports_unknown_files_changed_when_the_diff_lookup_fails(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh("pr", "diff", "--name-only", code=1, stderr="gh: rate limited")
    ef = exec_file(scenario, total_cost_usd=0.1, result="Opened the PR.")

    body = run_summary(scenario, "Coder", ef, "--issue", ISSUE, "--pr", PR)

    assert "**Files changed:** unknown" in body


def test_coder_summary_warns_when_cost_exceeds_the_warn_limit(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh("pr", "diff", "--name-only", stdout="")
    ef = exec_file(scenario, total_cost_usd=5.00, result="Opened the PR.")

    body = run_summary(scenario, "Coder", ef, "--issue", ISSUE, "--pr", PR, "--cost-warn", "1.00")

    assert "cost $5.0000 over the $1.00 warn limit" in body


def test_coder_summary_notes_a_missing_execution_file(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})

    body = run_summary(scenario, "Coder", "", "--issue", ISSUE)

    assert "No execution file — the agent step was killed" in body
    assert "**Cost:** $unknown" in body
    assert "_No final message — the run produced no result output._" in body


# --- Review phase ---------------------------------------------------------

def test_review_summary_reports_an_approval(scenario):
    scenario.gh("pr", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review("APPROVED")]])
    scenario.gh("pr", "view", "headRefOid", stdout={"headRefOid": HEAD})
    ef = exec_file(scenario, total_cost_usd=0.3, result="Approved.")

    body = run_summary(scenario, "Review", ef, "--pr", PR)

    assert "**Round:** initial review" in body
    assert "✅ Approved" in body


def test_review_summary_counts_prior_change_requests_excluding_this_heads_own(scenario):
    scenario.gh("pr", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[
        review("CHANGES_REQUESTED", commit="old-sha"),
        review("CHANGES_REQUESTED", commit=HEAD),
    ]])
    scenario.gh("pr", "view", "headRefOid", stdout={"headRefOid": HEAD})
    ef = exec_file(scenario, total_cost_usd=0.3, result="Changes requested.")

    body = run_summary(scenario, "Review", ef, "--pr", PR)

    assert "re-review (after 1 changes-requested)" in body
    assert "🔴 Changes requested" in body


def test_review_summary_flags_no_verdict_when_the_last_review_targets_an_older_commit(scenario):
    scenario.gh("pr", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review("APPROVED", commit="old-sha")]])
    scenario.gh("pr", "view", "headRefOid", stdout={"headRefOid": HEAD})
    ef = exec_file(scenario, total_cost_usd=0.3, result=None)

    body = run_summary(scenario, "Review", ef, "--pr", PR)

    assert "No verdict submitted — see the final message below." in body


def test_review_summary_falls_back_when_the_review_list_cannot_be_fetched(scenario):
    scenario.gh("pr", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", code=1, stderr="gh: rate limited")
    scenario.gh("pr", "view", "headRefOid", stdout={"headRefOid": HEAD})
    ef = exec_file(scenario, total_cost_usd=0.3, result="Timed out.")

    body = run_summary(scenario, "Review", ef, "--pr", PR)

    assert "**Round:** unavailable" in body
    assert "Review lookup failed — see the step log." in body


def test_review_summary_falls_back_when_the_pr_title_lookup_fails(scenario):
    scenario.gh("pr", "view", "title", code=1, stderr="gh: rate limited")
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review("APPROVED")]])
    scenario.gh("pr", "view", "headRefOid", stdout={"headRefOid": HEAD})
    ef = exec_file(scenario, total_cost_usd=0.3, result="Approved.")

    body = run_summary(scenario, "Review", ef, "--pr", PR)

    pr_line = next(line for line in body.splitlines() if line.startswith("**PR:**"))
    assert f"[#{PR}]" in pr_line
    assert "Add CSV export" not in pr_line


# --- Refinement phase -------------------------------------------------------

def test_refinement_summary_reports_the_refined_outcome(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:refined", "type:coding-task"))
    ef = exec_file(scenario, total_cost_usd=0.05, result="Refined the body.")

    body = run_summary(scenario, "Refinement", ef, "--issue", ISSUE)

    assert "Body refined" in body


def test_refinement_summary_reports_needs_attention(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:needs-attention"))
    ef = exec_file(scenario, total_cost_usd=0.05, result="Asked a clarifying question.")

    body = run_summary(scenario, "Refinement", ef, "--issue", ISSUE)

    assert "Stopped for clarification — see the final message below." in body


def test_refinement_summary_falls_back_to_no_terminal_state_when_labels_lookup_fails(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh("issue", "view", "labels", code=1, stderr="gh: rate limited")
    ef = exec_file(scenario, total_cost_usd=0.05, result="Crashed.")

    body = run_summary(scenario, "Refinement", ef, "--issue", ISSUE)

    assert "Label lookup failed — see the step log." in body


# --- Estimation phase -------------------------------------------------------

def test_estimation_summary_reports_the_size(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:estimated", "size:M"))
    ef = exec_file(scenario, total_cost_usd=0.05, result="Estimated M.")

    body = run_summary(scenario, "Estimation", ef, "--issue", ISSUE)

    assert "Estimate posted — `size:M`" in body


def test_estimation_summary_reports_ended_without_an_estimate(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:refined"))
    ef = exec_file(scenario, total_cost_usd=0.05, result=None)

    body = run_summary(scenario, "Estimation", ef, "--issue", ISSUE)

    assert "Ended without an estimate — see the final message below." in body


def test_estimation_summary_reports_needs_attention(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh("issue", "view", "labels", stdout=labels_payload("status:needs-attention"))
    ef = exec_file(scenario, total_cost_usd=0.05, result="Asked a clarifying question.")

    body = run_summary(scenario, "Estimation", ef, "--issue", ISSUE)

    assert "Stopped for clarification — see the final message below." in body


def test_estimation_summary_falls_back_when_labels_lookup_fails(scenario):
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})
    scenario.gh("issue", "view", "labels", code=1, stderr="gh: rate limited")
    ef = exec_file(scenario, total_cost_usd=0.05, result="Crashed.")

    body = run_summary(scenario, "Estimation", ef, "--issue", ISSUE)

    assert "Label lookup failed — see the step log." in body


def test_unknown_phase_is_a_hard_error(scenario):
    ef = exec_file(scenario, total_cost_usd=0.05, result="ok")
    step_summary = scenario.dir / "summary.md"
    step_summary.write_text("")

    result = scenario.run("pipeline.run_summary", "Bogus", ef, "--issue", ISSUE,
                          env={"GITHUB_STEP_SUMMARY": str(step_summary)})

    assert result.returncode != 0
    assert "unknown phase Bogus" in result.stderr
    assert step_summary.read_text() == ""
