"""The reviewer's check gate gets a PR number on workflow_dispatch, where `github.event.pull_request` is absent."""

import re
from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[2] / ".github/workflows/code-pipeline.yml").read_text()
PR_NUMBER = "${{ github.event.pull_request.number || inputs.pr_number }}"


def step(name: str) -> str:
    match = re.search(rf"      - name: {re.escape(name)}\n((?:        .*\n|\n)+)", WORKFLOW)
    assert match, f"step {name!r} not found"
    return match.group(1)


def test_wait_for_checks_receives_the_dispatch_pr_number():
    body = step("Wait for PR checks")
    assert f"PR_NUMBER: {PR_NUMBER}" in body
    assert '--pr "$PR_NUMBER"' in body


def test_route_red_checks_receives_the_dispatch_pr_number():
    body = step("Route red checks to a human")
    assert f"PR_NUMBER: {PR_NUMBER}" in body
    assert '--pr "$PR_NUMBER"' in body
