"""After estimation, `auto-proceed` hands enabled sizes straight to the coder."""

import pytest

from testkit.harness import Scenario, labels_payload

ISSUE = "7"


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def run(scenario: Scenario, *current: str, config: str = "/nonexistent/interns.yml"):
    scenario.gh("issue", "view", "labels", stdout=labels_payload(*current))
    return scenario.run("interns.entrypoint", "auto-proceed", "--issue", ISSUE,
                        env={"INTERNS_CONFIG": config})


@pytest.mark.parametrize("size", ["XS", "S", "M"])
def test_default_sizes_proceed_to_the_coder(scenario, size):
    run(scenario, "status:estimated", "type:coding-task", f"size:{size}")

    assert scenario.label_edits("issue") == [(ISSUE, {"status:ready"}, {"status:estimated"})]
    assert len(scenario.comments("issue")) == 1


@pytest.mark.parametrize("size", ["L", "XL"])
def test_large_sizes_wait_for_a_human_by_default(scenario, size):
    run(scenario, "status:estimated", "type:coding-task", f"size:{size}")

    assert scenario.label_edits("issue") == []
    assert scenario.comments("issue") == []


def test_bug_proceeds(scenario):
    run(scenario, "status:estimated", "type:bug", "size:S")

    assert scenario.label_edits("issue") == [(ISSUE, {"status:ready"}, {"status:estimated"})]


@pytest.mark.parametrize("type_label", ["type:spike", "type:epic"])
def test_non_coder_types_never_proceed(scenario, type_label):
    run(scenario, "status:estimated", type_label, "size:XS")

    assert scenario.label_edits("issue") == []


def test_issue_not_on_estimated_is_left_alone(scenario):
    run(scenario, "status:needs-attention", "type:coding-task", "size:XS")

    assert scenario.label_edits("issue") == []


def test_consumer_config_enables_a_larger_size(scenario, tmp_path):
    config = tmp_path / "interns.yml"
    config.write_text("auto_proceed:\n  L: true\n")

    run(scenario, "status:estimated", "type:coding-task", "size:L", config=str(config))

    assert scenario.label_edits("issue") == [(ISSUE, {"status:ready"}, {"status:estimated"})]


def test_consumer_config_disables_a_default_size(scenario, tmp_path):
    config = tmp_path / "interns.yml"
    config.write_text("auto_proceed:\n  XS: false\n")

    run(scenario, "status:estimated", "type:coding-task", "size:XS", config=str(config))

    assert scenario.label_edits("issue") == []
