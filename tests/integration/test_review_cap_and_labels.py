"""Two independent guardrails: the per-PR ceiling on automatic reviewer runs,
and syncing the versioned label manifest into a repo.
"""

import json

import pytest

from testkit.harness import REPO, Scenario

PR = "12"


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def review(login: str = "reviewer-bot") -> dict:
    return {"id": 1, "user": {"login": login}, "state": "CHANGES_REQUESTED", "commit_id": "sha"}


def test_review_cap_is_a_noop_below_the_limit(scenario):
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review(), review()]])

    result = scenario.run("interns.entrypoint", "check-review-cap", "--pr", PR)

    assert result.outputs == {"capped": "false"}
    assert scenario.calls("gh", "pr", "edit") == []
    assert scenario.comments("pr") == []


def test_review_cap_escalates_once_the_limit_is_reached(scenario):
    scenario.gh(f"repos/{REPO}/pulls/{PR}/reviews", stdout=[[review(), review()]])
    scenario.gh("pr", "view", "labels", stdout={"labels": [{"name": "pr:in-review"}]})

    result = scenario.run("interns.entrypoint", "check-review-cap", "--pr", PR,
                          "--max-reviews", "2")

    assert result.outputs == {"capped": "true"}
    assert scenario.label_edits("pr") == [(PR, {"pr:needs-attention"}, {"pr:in-review"})]
    (number, body), = scenario.comments("pr")
    assert number == PR and "Automatic review limit (2) reached" in body


def test_review_cap_accepts_a_precomputed_count_without_refetching(scenario):
    scenario.gh("pr", "view", "labels", stdout={"labels": []})

    result = scenario.run("interns.entrypoint", "check-review-cap", "--pr", PR, "--count", "5")

    assert result.outputs == {"capped": "true"}
    assert scenario.calls("gh", "api") == []


def _manifest(path, *labels):
    path.write_text(json.dumps({"version": 1, "labels": list(labels)}))


def test_sync_labels_creates_missing_ones(scenario):
    manifest = scenario.workspace / "labels.json"
    _manifest(manifest, {"name": "status:ready", "color": "00ff00", "description": "Ready to code"})
    scenario.gh(f"repos/{REPO}/labels?per_page=100", stdout=[[]])
    scenario.gh("label", "create")

    result = scenario.run("interns.entrypoint", "sync-labels", str(manifest), env={"GH_TOKEN": "x"})

    assert result.returncode == 0
    (create,) = scenario.calls("gh", "label", "create")
    assert create == ["label", "create", "status:ready", "--repo", REPO,
                       "--color", "00ff00", "--description", "Ready to code"]
    assert "1 created, 0 updated, 0 unchanged" in result.stdout


def test_sync_labels_updates_a_drifted_color_or_description(scenario):
    manifest = scenario.workspace / "labels.json"
    _manifest(manifest, {"name": "status:ready", "color": "00ff00", "description": "Ready to code"})
    scenario.gh(f"repos/{REPO}/labels?per_page=100",
                stdout=[[{"name": "status:ready", "color": "ff0000", "description": "old"}]])
    scenario.gh("label", "edit")

    result = scenario.run("interns.entrypoint", "sync-labels", str(manifest), env={"GH_TOKEN": "x"})

    assert result.returncode == 0
    (edit,) = scenario.calls("gh", "label", "edit")
    assert edit == ["label", "edit", "status:ready", "--repo", REPO,
                     "--color", "00ff00", "--description", "Ready to code"]
    assert "0 created, 1 updated, 0 unchanged" in result.stdout


def test_sync_labels_leaves_a_matching_label_alone(scenario):
    manifest = scenario.workspace / "labels.json"
    _manifest(manifest, {"name": "status:ready", "color": "00FF00", "description": "Ready to code"})
    scenario.gh(f"repos/{REPO}/labels?per_page=100",
                stdout=[[{"name": "status:ready", "color": "00ff00", "description": "Ready to code"}]])

    result = scenario.run("interns.entrypoint", "sync-labels", str(manifest), env={"GH_TOKEN": "x"})

    assert result.returncode == 0
    assert scenario.calls("gh", "label") == []
    assert "0 created, 0 updated, 1 unchanged" in result.stdout


def test_sync_labels_never_deletes_a_label_missing_from_the_manifest(scenario):
    manifest = scenario.workspace / "labels.json"
    _manifest(manifest, {"name": "status:ready", "color": "00ff00", "description": ""})
    scenario.gh(f"repos/{REPO}/labels?per_page=100",
                stdout=[[{"name": "status:ready", "color": "00ff00", "description": ""},
                         {"name": "consumer:custom", "color": "abcdef", "description": "not in the manifest"}]])

    result = scenario.run("interns.entrypoint", "sync-labels", str(manifest), env={"GH_TOKEN": "x"})

    assert result.returncode == 0
    assert scenario.calls("gh", "label") == []


def test_sync_labels_fails_on_a_malformed_manifest(scenario):
    manifest = scenario.workspace / "labels.json"
    manifest.write_text(json.dumps({"labels": "not-a-list"}))

    result = scenario.run("interns.entrypoint", "sync-labels", str(manifest), env={"GH_TOKEN": "x"})

    assert result.returncode == 1
    assert "malformed manifest" in result.stderr
    assert scenario.calls("gh") == []


def test_sync_labels_fails_on_a_missing_manifest(scenario):
    result = scenario.run("interns.entrypoint", "sync-labels", str(scenario.workspace / "nope.json"),
                          env={"GH_TOKEN": "x"})

    assert result.returncode == 1
    assert "no such manifest" in result.stderr


def test_sync_labels_requires_a_repository(scenario):
    manifest = scenario.workspace / "labels.json"
    _manifest(manifest, {"name": "status:ready", "color": "00ff00", "description": ""})

    result = scenario.run("interns.entrypoint", "sync-labels", str(manifest),
                          env={"GH_TOKEN": "x", "GITHUB_REPOSITORY": ""})

    assert result.returncode == 1
    assert "GITHUB_REPOSITORY unset" in result.stderr
    assert scenario.calls("gh") == []


def test_sync_labels_requires_a_token(scenario):
    manifest = scenario.workspace / "labels.json"
    _manifest(manifest, {"name": "status:ready", "color": "00ff00", "description": ""})

    result = scenario.run("interns.entrypoint", "sync-labels", str(manifest), env={"GH_TOKEN": ""})

    assert result.returncode == 1
    assert "GH_TOKEN unset" in result.stderr
    assert scenario.calls("gh") == []
