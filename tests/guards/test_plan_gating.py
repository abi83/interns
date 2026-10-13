"""Skip/run decisions are made once, in the plan job, and agent jobs gate on its outputs
instead of repeating per-step conditions."""

import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"
CODE = (WORKFLOWS / "code-pipeline.yml").read_text()
ISSUE = (WORKFLOWS / "issue-pipeline.yml").read_text()

STEP_SKIP_CONDITION = re.compile(r"if:.*steps\.\w+\.outputs\.(skip|capped|ok)\b")
GATED_JOBS = [
    (CODE, "coder"),
    (CODE, "reviewer"),
    (CODE, "pr_closed"),
    (ISSUE, "refine"),
    (ISSUE, "estimate"),
]


def job_block(workflow: str, job: str) -> str:
    match = re.search(rf"^  {job}:\n((?:    .*\n|\n)+)", workflow, re.MULTILINE)
    assert match, f"job {job!r} not found"
    return match.group(1)


def test_guard_detects_a_step_skip_condition():
    assert STEP_SKIP_CONDITION.search("if: steps.guard.outputs.skip != 'true'")
    assert not STEP_SKIP_CONDITION.search("if: needs.plan.outputs.skip == 'false'")


def test_no_step_condition_inspects_a_skip_flag():
    for name, workflow in (("code-pipeline.yml", CODE), ("issue-pipeline.yml", ISSUE)):
        assert not STEP_SKIP_CONDITION.findall(workflow), f"{name}: gate the job on needs.plan.outputs instead"


def test_agent_jobs_need_plan_and_gate_on_its_outputs():
    for workflow, job in GATED_JOBS:
        block = job_block(workflow, job)
        assert "    needs: plan\n" in block, f"{job} must need plan"
        assert f"    if: needs.plan.outputs.job == '{job}'\n" in block, f"{job} must gate on the plan's job"


def test_no_job_condition_inspects_the_event_besides_the_plan_filter():
    for name, workflow in (("code-pipeline.yml", CODE), ("issue-pipeline.yml", ISSUE)):
        without_plan = workflow.replace(job_block(workflow, "plan"), "")
        offenders = re.findall(r"^    if:.*github\.event.*$", without_plan, re.MULTILINE)
        assert not offenders, f"{name}: route events in domain/routing.py instead: {offenders}"
