"""The pipeline's `gh` parsing against responses captured from the real CLI.

Fixtures are raw `gh` stdout (regenerate with tests/contract/capture.py). The
fake `gh` replays them, so the real `pipeline.gh` argv building and JSON
handling run against real shapes rather than hand-written ones.
"""

import json
from pathlib import Path

import pytest
from interns_install import gh_admin
from interns import gh, gh_query, labels, verdict, wait_for_checks

from testkit.harness import Scenario

FIXTURES = Path(__file__).parent / "fixtures"
REPO = "abi83/interns"


def fixture(name: str) -> str:
    return (FIXTURES / f"{name}.json").read_text()


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    scenario = Scenario(tmp_path)
    scenario.activate(monkeypatch)
    yield scenario
    scenario.assert_all_matched()


def test_current_repo_reads_owner_type_from_the_repos_api(scenario):
    scenario.gh("repo", "view", stdout=fixture("repo_view"))
    scenario.gh("api", f"repos/{REPO}", stdout=fixture("api_repo"))

    repo = gh_admin.current_repo(REPO)

    assert (repo.owner, repo.name, repo.is_org) == ("abi83", "interns", False)


def test_default_branch(scenario):
    scenario.gh("api", f"repos/{REPO}", stdout=fixture("api_repo"))

    assert gh.default_branch(REPO) == json.loads(fixture("api_repo"))["default_branch"]


def test_issue_labels_and_title(scenario):
    scenario.gh("issue", "view", stdout=fixture("issue_view"))

    assert labels.issue_labels(REPO, 155) == [label["name"] for label in json.loads(fixture("issue_view"))["labels"]]
    assert gh.issue_view(REPO, 155, ["title"])["title"]


def test_pr_lookups(scenario):
    scenario.gh("pr", "view", stdout=fixture("pr_view"))
    pr = json.loads(fixture("pr_view"))

    assert gh_query.head_ref(REPO, 199) == pr["headRefName"]
    assert gh_query.head_sha(REPO, 199) == pr["headRefOid"]
    assert gh_query.closing_issue(REPO, 199) == str(pr["closingIssuesReferences"][0]["number"])
    assert labels.pr_labels(REPO, 199) == [label["name"] for label in pr["labels"]]


def test_pr_for_issue_finds_the_pr_closing_it(scenario):
    scenario.gh("pr", "list", stdout=fixture("pr_list"))
    first = json.loads(fixture("pr_list"))[0]
    issue = first["closingIssuesReferences"][0]["number"]

    assert gh_query.pr_for_issue(REPO, issue) == {"pr_number": str(first["number"]), "head_ref": first["headRefName"]}


def test_pr_checks_classify_by_bucket(scenario):
    scenario.gh("pr", "checks", stdout=fixture("pr_checks"))

    checks = gh.pr_checks(REPO, 199)
    summary = wait_for_checks._classify(checks, run_id="", ignore=[])

    assert summary.total == len(json.loads(fixture("pr_checks")))
    assert summary.red == [] and summary.pending == []


def test_reviews_parse_into_verdict_inputs(scenario):
    scenario.gh(f"repos/{REPO}/pulls/199/reviews", stdout=fixture("pr_reviews"))

    reviews = verdict.all_reviews(REPO, 199)

    assert reviews
    assert all(r.login and r.state and r.commit_id for r in reviews)
    assert verdict.verdict_for_head(reviews, reviews[-1].commit_id) == reviews[-1].state


def test_label_list_reads_name_color_and_description(scenario):
    scenario.gh(f"repos/{REPO}/labels?per_page=100", stdout=fixture("labels"))

    listed = gh.label_list(REPO)

    assert listed
    assert all({"name", "color", "description"} == set(entry) for entry in listed)
    assert gh.label_names(REPO) == [entry["name"] for entry in listed]
