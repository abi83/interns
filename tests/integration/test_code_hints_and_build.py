"""Deterministic pre-coder prep: the Makefile-stub check and the
commit-type/branch-name hints derived from the issue's type label.
"""

import pytest

from testkit.harness import Scenario, labels_payload

ISSUE = "7"


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def test_build_config_is_unconfigured_with_the_stub_marker(scenario):
    (scenario.workspace / "Makefile").write_text("test:\n\t@echo INTERNS: not configured\n")

    result = scenario.run("pipeline.check_build_config", str(scenario.workspace))

    assert result.outputs == {"configured": "false"}


def test_build_config_is_configured_once_the_stub_is_replaced(scenario):
    (scenario.workspace / "Makefile").write_text("test:\n\tpytest\n")

    result = scenario.run("pipeline.check_build_config", str(scenario.workspace))

    assert result.outputs == {"configured": "true"}


def test_build_config_is_unconfigured_with_no_makefile_at_all(scenario):
    result = scenario.run("pipeline.check_build_config", str(scenario.workspace))

    assert result.outputs == {"configured": "false"}


def test_bug_label_derives_a_fix_hint_and_branch(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:bug", "status:ready"))
    scenario.gh("issue", "view", "title", stdout={"title": "Export drops rows with commas"})

    result = scenario.run("pipeline.derive_code_hints", ISSUE)

    assert result.returncode == 0
    assert result.outputs["commit_type_hint"] == "fix:"
    assert result.outputs["branch"] == "fix/issue-7-export-drops-rows-with-commas"


def test_coding_task_label_derives_a_feat_hint_and_branch(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:coding-task", "status:ready"))
    scenario.gh("issue", "view", "title", stdout={"title": "Add CSV export"})

    result = scenario.run("pipeline.derive_code_hints", ISSUE)

    assert result.returncode == 0
    assert result.outputs["commit_type_hint"] == "feat:"
    assert result.outputs["branch"] == "feat/issue-7-add-csv-export"


def test_neither_type_label_fails_instead_of_guessing(scenario):
    scenario.gh("issue", "view", "labels", stdout=labels_payload("type:spike", "status:ready"))

    result = scenario.run("pipeline.derive_code_hints", ISSUE)

    assert result.returncode != 0
    assert "neither type:bug nor type:coding-task" in result.stderr
    assert result.outputs == {}
