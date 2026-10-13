"""`routing` handles every event the caller templates subscribe to, and routes only on labels that exist."""

import json
import re
from pathlib import Path

import pytest

from interns.domain import routing

ROOT = Path(__file__).resolve().parents[2]
ROUTED_TEMPLATES = ["code-pipeline.yml", "issue-pipeline.yml"]
LABELS = {label["name"] for label in json.loads((ROOT / ".github/labels.json").read_text())["labels"]}


def subscribed_actions(template: str) -> dict[str, set[str]]:
    """Event name -> the `types:` the template subscribes to (empty when it takes no types)."""
    block = re.search(r"^on:\n((?:  .*\n|\n)+)", template, re.MULTILINE)
    assert block, "no on: block"
    subscribed: dict[str, set[str]] = {}
    for event, body in re.findall(r"^  (\w+):\n?((?:    .*\n)*)", block.group(1), re.MULTILINE):
        types = re.search(r"types: \[(.*)\]", body)
        subscribed[event] = {t.strip() for t in types.group(1).split(",")} if types else set()
    return subscribed


def test_guard_reads_events_and_types():
    template = "on:\n  issues:\n    types: [labeled]\n  pull_request:\n    types: [opened, closed]\n  workflow_dispatch:\n    inputs:\n      x:\n        type: string\n\njobs:\n"
    assert subscribed_actions(template) == {
        "issues": {"labeled"},
        "pull_request": {"opened", "closed"},
        "workflow_dispatch": set(),
    }


@pytest.mark.parametrize("name", ROUTED_TEMPLATES)
def test_every_subscribed_event_and_action_is_handled_by_route(name: str):
    subscribed = subscribed_actions((ROOT / "templates/workflows" / name).read_text())
    assert subscribed
    for event, actions in subscribed.items():
        assert event in routing.SUPPORTED_ACTIONS, f"{name}: route() does not handle the {event} event"
        unhandled = actions - routing.SUPPORTED_ACTIONS[event]
        assert not unhandled, f"{name}: route() does not handle {event} actions {sorted(unhandled)}"


def test_every_routed_label_exists_in_the_label_manifest():
    missing = set(routing.LABEL_JOBS) - LABELS
    assert not missing, f"labels.json lacks routed labels: {sorted(missing)}"


@pytest.mark.parametrize("name", ROUTED_TEMPLATES)
def test_plan_filter_only_names_routed_labels(name: str):
    workflow = (ROOT / ".github/workflows" / name).read_text()
    plan_filter = re.search(r"^  plan:\n(?:    #.*\n)*    if: (.*(?:\n      .*)*)", workflow, re.MULTILINE)
    assert plan_filter, f"{name}: plan job has no filter"
    named = set(re.findall(r"label\.name == '([^']+)'", plan_filter.group(1)))
    assert named <= set(routing.LABEL_JOBS), f"{name}: plan filter names unrouted labels {sorted(named - set(routing.LABEL_JOBS))}"
