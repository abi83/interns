"""Contract tests for push-path pipeline operations.

These tests run pipeline.push functions in-process with fake git and gh on PATH
(via Scenario.activate), so the actual subprocess argument shapes are verified
against realistic fake responses rather than hand-written subprocess mocks.
"""

import json

import pytest
from pipeline import gh, labels, push
from pipeline.gh import GhCommandError, InvalidInputError, PushRefusedError

from testkit.harness import REPO, Scenario

_API_REPO = json.dumps({"default_branch": "main", "name": "widgets", "owner": {"login": "acme"}})


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
    scenario.gh("api", f"repos/{REPO}", stdout=_API_REPO)
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
    scenario.gh("api", f"repos/{REPO}", stdout=_API_REPO)
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="feat/my-branch")
    scenario.git("fetch", stdout="")
    scenario.git("merge-base", stdout="abc123")
    scenario.git("rev-parse", "HEAD", stdout="abc123")  # same as base = nothing to push

    with pytest.raises(PushRefusedError, match="nothing to push"):
        push.push_branch(REPO, "")


def test_push_branch_rejects_protected_path(scenario):
    scenario.gh("api", f"repos/{REPO}", stdout=_API_REPO)
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="feat/my-branch")
    scenario.git("fetch", stdout="")
    scenario.git("merge-base", stdout="abc123")
    scenario.git("rev-parse", "HEAD", stdout="def456")
    scenario.git("log", stdout="chore: update workflow\n")
    scenario.git("reset", stdout="")
    scenario.git("commit", stdout="")
    scenario.git("diff-tree", stdout=".github/workflows/ci.yml")
    scenario.git("reset", stdout="")  # rollback squash before raising

    with pytest.raises(PushRefusedError, match="protected paths"):
        push.push_branch(REPO, "")


def test_push_branch_surfaces_git_error(scenario):
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="feat/my-branch")
    scenario.gh("api", f"repos/{REPO}", stdout=_API_REPO)
    scenario.git("fetch", code=1, stderr="fatal: unable to access 'origin'")

    with pytest.raises(GhCommandError, match="unable to access"):
        push.push_branch(REPO, "")


# ---------------------------------------------------------------------------
# pr_open_for_issue
# ---------------------------------------------------------------------------


def test_pr_open_for_issue_appends_closes_and_opens_pr(scenario):
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="feat/issue-42")
    scenario.gh("api", f"repos/{REPO}", stdout=_API_REPO)
    scenario.gh("pr", "create", stdout="https://github.example/acme/widgets/pull/99")

    result = push.pr_open_for_issue(REPO, "", 42, "feat: implement thing", "This implements the thing.")

    assert result == "https://github.example/acme/widgets/pull/99"
    pr_create_calls = scenario.calls("gh", "pr", "create")
    assert pr_create_calls
    argv = pr_create_calls[0]
    body = argv[argv.index("--body") + 1]
    assert "Closes #42" in body
    assert "This implements the thing." in body
    head = argv[argv.index("--head") + 1]
    assert head == "feat/issue-42"
    base = argv[argv.index("--base") + 1]
    default = json.loads(_API_REPO)["default_branch"]
    assert base == default


def test_pr_open_for_issue_rejects_detached_head(scenario):
    scenario.git("rev-parse", "--abbrev-ref", "HEAD", stdout="HEAD")

    with pytest.raises(GhCommandError, match="detached HEAD"):
        push.pr_open_for_issue(REPO, "", 42, "feat: add thing", "Body text here.")


# ---------------------------------------------------------------------------
# issue_edit_validated
# ---------------------------------------------------------------------------


def test_issue_edit_validated_forwards_body_and_title(scenario):
    # gh issue edit is QUIET — no stub needed; verify the args it receives.
    result = gh.issue_edit_validated(REPO, 5, body="New body text", title="New title")

    edits = scenario.calls("gh", "issue", "edit")
    assert edits, "expected a gh issue edit call"
    argv = edits[0]
    assert argv[argv.index("--body") + 1] == "New body text"
    assert argv[argv.index("--title") + 1] == "New title"
    assert result  # non-empty success string


def test_issue_edit_validated_body_only(scenario):
    result = gh.issue_edit_validated(REPO, 5, body="New body text")

    edits = scenario.calls("gh", "issue", "edit")
    assert edits
    assert "--title" not in edits[0]
    assert result


# ---------------------------------------------------------------------------
# pr_submit_review
# ---------------------------------------------------------------------------


def test_pr_submit_review_posts_to_reviews_endpoint(scenario):
    scenario.gh("api", "POST", f"repos/{REPO}/pulls/7/reviews", stdout='{"id": 1}')

    result = gh.pr_submit_review(REPO, 7, "APPROVE", "Looks good")

    assert result == {"id": 1}
    stdin = scenario.stdin_of("gh", "api")
    payload = json.loads(stdin)
    assert payload["event"] == "APPROVE"
    assert payload["body"] == "Looks good"
    assert payload["comments"] == []


def test_pr_submit_review_includes_inline_comments(scenario):
    scenario.gh("api", "POST", f"repos/{REPO}/pulls/7/reviews", stdout='{"id": 2}')

    gh.pr_submit_review(REPO, 7, "REQUEST_CHANGES", "Needs work",
                        comments=[{"path": "foo.py", "line": 3, "body": "fix this"}])

    payload = json.loads(scenario.stdin_of("gh", "api"))
    assert payload["event"] == "REQUEST_CHANGES"
    assert len(payload["comments"]) == 1
    assert payload["comments"][0]["path"] == "foo.py"


# ---------------------------------------------------------------------------
# edit_issue_labels_validated
# ---------------------------------------------------------------------------


def test_edit_issue_labels_validated_adds_and_removes(scenario):
    labels_fixture = json.dumps([[
        {"name": "type:bug", "color": "d73a4a", "description": ""},
        {"name": "status:ready", "color": "0e8a16", "description": ""},
    ]])
    scenario.gh("api", f"repos/{REPO}/labels?per_page=100", stdout=labels_fixture)
    scenario.gh("issue", "view", stdout=json.dumps({"labels": [{"name": "type:bug"}]}))
    # gh issue edit is QUIET

    result = labels.edit_issue_labels_validated(REPO, 7, add=["status:ready"], remove=["type:bug"])

    assert "Added: status:ready" in result
    assert "Removed: type:bug" in result


# ---------------------------------------------------------------------------
# apply_refinement
# ---------------------------------------------------------------------------


def test_apply_refinement_refined_applies_transition(scenario):
    scenario.gh("issue", "view", stdout=json.dumps({"labels": [{"name": "status:needs-refinement"}]}))
    # gh issue edit is QUIET

    result = labels.apply_refinement(REPO, 5, "refined", "type:coding-task")

    edits = scenario.calls("gh", "issue", "edit")
    assert edits
    argv = edits[0]
    added = {argv[i + 1] for i, a in enumerate(argv) if a == "--add-label"}
    assert "status:refined" in added
    assert "type:coding-task" in added
    assert "refined" in result


def test_apply_refinement_needs_attention_applies_transition(scenario):
    scenario.gh("issue", "view", stdout=json.dumps({"labels": [{"name": "status:needs-refinement"}]}))

    result = labels.apply_refinement(REPO, 5, "needs-attention")

    edits = scenario.calls("gh", "issue", "edit")
    assert edits
    argv = edits[0]
    added = {argv[i + 1] for i, a in enumerate(argv) if a == "--add-label"}
    assert "status:needs-attention" in added
    assert "needs-attention" in result


# ---------------------------------------------------------------------------
# apply_estimation
# ---------------------------------------------------------------------------


def test_apply_estimation_estimated_applies_size_transition(scenario):
    scenario.gh("issue", "view", stdout=json.dumps({"labels": [{"name": "status:refined"}]}))

    result = labels.apply_estimation(REPO, 7, "estimated", "Low", "Mid", "Low", "Low")

    edits = scenario.calls("gh", "issue", "edit")
    assert edits
    argv = edits[0]
    added = {argv[i + 1] for i, a in enumerate(argv) if a == "--add-label"}
    assert "status:estimated" in added
    assert any(a.startswith("size:") for a in added)
    assert "size:S" in result


def test_apply_estimation_needs_attention_applies_transition(scenario):
    scenario.gh("issue", "view", stdout=json.dumps({"labels": [{"name": "status:refined"}]}))

    result = labels.apply_estimation(REPO, 7, "needs-attention")

    edits = scenario.calls("gh", "issue", "edit")
    assert edits
    assert "needs-attention" in result


def test_pr_open_for_issue_rejects_multiline_title():
    with pytest.raises(InvalidInputError, match="single line"):
        push.pr_open_for_issue(REPO, "", 42, "line one\nline two", "Body text here.")
