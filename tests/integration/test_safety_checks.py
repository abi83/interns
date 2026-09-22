"""Presence check for the pipeline's required secrets and Actions variables.
A token that can't even list them is a warning, not a failure -- GITHUB_TOKEN
is never granted that scope -- but a definitively missing one still fails.
"""

import pytest

from testkit.harness import REPO, Scenario

SECRETS_PATH = f"repos/{REPO}/actions/secrets"
VARS_PATH = f"repos/{REPO}/actions/variables"

ENV = {"GH_TOKEN": "tok", "REQUIRED_SECRETS": "TOKEN_A TOKEN_B", "REQUIRED_VARS": "CLIENT_ID"}


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def test_passes_when_all_required_secrets_and_vars_are_present(scenario):
    scenario.gh(SECRETS_PATH, stdout="TOKEN_A\nTOKEN_B\nEXTRA\n")
    scenario.gh(VARS_PATH, stdout="CLIENT_ID\n")

    result = scenario.run("pipeline.entrypoint", "safety-checks", env=ENV)

    assert result.returncode == 0
    assert "all safety checks passed" in result.stdout


def test_fails_on_a_missing_secret(scenario):
    scenario.gh(SECRETS_PATH, stdout="TOKEN_A\n")
    scenario.gh(VARS_PATH, stdout="CLIENT_ID\n")

    result = scenario.run("pipeline.entrypoint", "safety-checks", env=ENV)

    assert result.returncode == 1
    assert "missing repo secret(s): TOKEN_B" in result.stderr
    assert "1 safety check(s) failed" in result.stderr


def test_fails_on_a_missing_variable(scenario):
    scenario.gh(SECRETS_PATH, stdout="TOKEN_A\nTOKEN_B\n")
    scenario.gh(VARS_PATH, stdout="")

    result = scenario.run("pipeline.entrypoint", "safety-checks", env=ENV)

    assert result.returncode == 1
    assert "missing repo variable(s): CLIENT_ID" in result.stderr


def test_reports_both_missing_secrets_and_variables_together(scenario):
    scenario.gh(SECRETS_PATH, stdout="")
    scenario.gh(VARS_PATH, stdout="")

    result = scenario.run("pipeline.entrypoint", "safety-checks", env=ENV)

    assert result.returncode == 1
    assert "missing repo secret(s): TOKEN_A TOKEN_B" in result.stderr
    assert "missing repo variable(s): CLIENT_ID" in result.stderr
    assert "2 safety check(s) failed" in result.stderr


def test_warns_instead_of_failing_when_the_token_cannot_list_secrets(scenario):
    scenario.gh(SECRETS_PATH, code=1, stderr="HTTP 403: Resource not accessible")
    scenario.gh(VARS_PATH, stdout="CLIENT_ID\n")

    result = scenario.run("pipeline.entrypoint", "safety-checks", env=ENV)

    assert result.returncode == 0
    assert "list_secret_names unavailable" in result.stderr
    assert "all safety checks passed" in result.stdout


def test_warns_instead_of_failing_when_the_token_cannot_list_variables(scenario):
    scenario.gh(SECRETS_PATH, stdout="TOKEN_A\nTOKEN_B\n")
    scenario.gh(VARS_PATH, code=1, stderr="HTTP 403: Resource not accessible")

    result = scenario.run("pipeline.entrypoint", "safety-checks", env=ENV)

    assert result.returncode == 0
    assert "list_variable_names unavailable" in result.stderr
    assert "all safety checks passed" in result.stdout


def test_requires_a_repo_and_token(scenario):
    result = scenario.run("pipeline.entrypoint", "safety-checks", env={**ENV, "GH_TOKEN": ""})

    assert result.returncode == 1
    assert "GH_TOKEN unset" in result.stderr
    assert scenario.calls("gh") == []
