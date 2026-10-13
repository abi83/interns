"""A failed initial coder run saves its work as a draft PR, the failure comment links it, and the caller template reviews it once marked ready."""

import re
from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[2] / ".github/workflows/code-pipeline.yml").read_text()


def step(name: str) -> str:
    match = re.search(rf"      - name: {re.escape(name)}\n((?:        .*\n|\n)+)", WORKFLOW)
    assert match, f"step {name!r} not found"
    return match.group(1)


def test_draft_step_runs_only_when_the_initial_claude_step_failed():
    match = re.search(r"if: (.*)", step("Save unfinished work as draft PR"))
    assert match
    condition = match.group(1)
    assert "failure()" in condition
    assert "steps.claude_initial.outcome == 'failure'" in condition


def test_draft_step_opens_the_pr_as_the_coder_app_and_passes_the_title_through_env():
    body = step("Save unfinished work as draft PR")
    assert "GH_TOKEN: ${{ steps.coder_token.outputs.token }}" in body
    assert 'ISSUE_TITLE: ${{ steps.issue.outputs.title }}' in body
    assert '--issue-title "$ISSUE_TITLE"' in body
    assert "save-draft-pr" in body


def test_failure_comment_receives_the_draft_url_from_a_step_that_ran_before_it():
    assert WORKFLOW.index("name: Save unfinished work as draft PR") < WORKFLOW.index("name: Flag failure")
    assert '--draft-pr-url "${{ steps.draft_pr.outputs.draft_pr_url }}"' in step("Flag failure")


def test_caller_template_reviews_a_draft_once_it_is_marked_ready():
    template = (Path(__file__).resolve().parents[2] / "templates/workflows/code-pipeline.yml").read_text()
    assert "ready_for_review" in template
