"""Contract tests for push-path pipeline operations.

These tests run pipeline.push functions in-process with fake git and gh on PATH
(via Scenario.activate), so the actual subprocess argument shapes are verified
against realistic fake responses rather than hand-written subprocess mocks.
"""

import json
from pathlib import Path

import pytest
from pipeline import push
from pipeline.gh import GhCommandError, InvalidInputError, PushRefusedError

from testkit.harness import Scenario

FIXTURES = Path(__file__).parent / "fixtures"
REPO = "abi83/interns"


def fixture(name: str) -> str:
    return (FIXTURES / f"{name}.json").read_text()


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    s = Scenario(tmp_path)
    s.activate(monkeypatch)
    yield s
    s.assert_all_matched()


# ---------------------------------------------------------------------------
# push_branch
# ---------------------------------------------------------------------------


def test_push_branch_squashes_and_pushes(scenario):
    scenario.gh("api", f"repos/{REPO}", stdout=fixture("api_repo"))
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="feat/add-thing")
    scenario.git("fetch", stdout="")
    scenario.git("merge-base", stdout="abc123")
    scenario.git("rev-parse", "HEAD", stdout="def456")
    scenario.git("log", stdout="feat: add thing\n")
    scenario.git("reset", stdout="")
    scenario.git("commit", stdout="")
    scenario.git("diff-tree", stdout="src/pipeline/foo.py")
    scenario.git("push", stdout="")

    result = push.push_branch(REPO, "")

    assert "feat/add-thing" in result
    push_calls = scenario.calls("git", "push")
    assert any("feat/add-thing" in arg for args in push_calls for arg in args)


def test_push_branch_rejects_main(scenario):
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="main")

    with pytest.raises(PushRefusedError, match="Refusing"):
        push.push_branch(REPO, "")


def test_push_branch_rejects_no_commits(scenario):
    scenario.gh("api", f"repos/{REPO}", stdout=fixture("api_repo"))
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="feat/my-branch")
    scenario.git("fetch", stdout="")
    scenario.git("merge-base", stdout="abc123")
    scenario.git("rev-parse", "HEAD", stdout="abc123")  # same as base = nothing to push

    with pytest.raises(PushRefusedError, match="nothing to push"):
        push.push_branch(REPO, "")


def test_push_branch_rejects_protected_path(scenario):
    scenario.gh("api", f"repos/{REPO}", stdout=fixture("api_repo"))
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="feat/my-branch")
    scenario.git("fetch", stdout="")
    scenario.git("merge-base", stdout="abc123")
    scenario.git("rev-parse", "HEAD", stdout="def456")
    scenario.git("log", stdout="chore: update workflow\n")
    scenario.git("reset", stdout="")
    scenario.git("commit", stdout="")
    scenario.git("diff-tree", stdout=".github/workflows/ci.yml")

    with pytest.raises(PushRefusedError, match="protected paths"):
        push.push_branch(REPO, "")


def test_push_branch_surfaces_git_error(scenario):
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="feat/my-branch")
    scenario.gh("api", f"repos/{REPO}", stdout=fixture("api_repo"))
    scenario.git("fetch", code=1, stderr="fatal: unable to access 'origin'")

    with pytest.raises(GhCommandError, match="unable to access"):
        push.push_branch(REPO, "")


# ---------------------------------------------------------------------------
# pr_open_for_issue
# ---------------------------------------------------------------------------


def test_pr_open_for_issue_appends_closes_and_opens_pr(scenario):
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="feat/issue-42")
    scenario.gh("api", f"repos/{REPO}", stdout=fixture("api_repo"))
    scenario.gh("pr", "create", stdout="https://github.com/abi83/interns/pull/99")

    result = push.pr_open_for_issue(REPO, "", 42, "feat: implement thing", "This implements the thing.")

    assert result == "https://github.com/abi83/interns/pull/99"
    pr_create_calls = scenario.calls("gh", "pr", "create")
    assert pr_create_calls
    argv = pr_create_calls[0]
    body = argv[argv.index("--body") + 1]
    assert "Closes #42" in body
    assert "This implements the thing." in body
    head = argv[argv.index("--head") + 1]
    assert head == "feat/issue-42"
    base = argv[argv.index("--base") + 1]
    default = json.loads(fixture("api_repo"))["default_branch"]
    assert base == default


def test_pr_open_for_issue_rejects_detached_head(scenario):
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="HEAD")

    with pytest.raises(GhCommandError, match="detached HEAD"):
        push.pr_open_for_issue(REPO, "", 42, "feat: add thing", "Body text here.")


def test_pr_open_for_issue_rejects_multiline_title(scenario):
    with pytest.raises(InvalidInputError, match="single line"):
        push.pr_open_for_issue(REPO, "", 42, "line one\nline two", "Body text here.")
