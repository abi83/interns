"""The checkout credential is gone from the working tree before any consumer or agent code runs,
and the coder's commits carry its own identity."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = (ROOT / ".github/workflows/code-pipeline.yml").read_text()
ACTION = (ROOT / ".github/actions/prepare-agent-git/action.yml").read_text()
CODER = WORKFLOW.split("\n  coder:\n", 1)[1].split("\n  reviewer:\n", 1)[0]


def test_credential_is_dropped_before_consumer_setup_and_both_coder_runs():
    prepare = CODER.index("uses: ./.interns/.github/actions/prepare-agent-git")
    assert prepare < CODER.index("name: Install dependencies (make setup)")
    assert prepare < CODER.index("id: coder_initial")
    assert prepare < CODER.index("id: coder_fix")


def test_prepare_action_unsets_the_checkout_header_and_verifies_it_is_gone():
    assert "--unset-all http.https://github.com/.extraheader" in ACTION
    assert "git config --get-regexp 'extraheader'" in ACTION


def test_coder_runs_get_the_coder_token_not_the_default_token():
    for step_id in ("coder_initial", "coder_fix"):
        block = CODER.split(f"id: {step_id}", 1)[1].split("\n      - name: ", 1)[0]
        assert "GH_TOKEN: ${{ steps.coder_token.outputs.token }}" in block
