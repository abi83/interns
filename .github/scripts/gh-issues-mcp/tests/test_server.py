"""Tests for gh-issues MCP server."""

import json
import os
import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

import server
from pipeline import fetch_issue
from server import (
    GhCommandError,
    InlineComment,
    InvalidInputError,
    PushRefusedError,
    _load_label_names,
    apply_estimation_outcome,
    apply_refinement_outcome,
    comment_issue,
    comment_pr,
    edit_issue,
    edit_issue_labels,
    list_issues,
    open_pr,
    push_branch,
    submit_pr_review,
    view_issue,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_proc(stdout: str = "", returncode: int = 0, stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    m.stderr = stderr
    return m


def _gh_failure(stderr: str) -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(1, ["gh"], stderr=stderr)


def _issue_labels_proc(*names: str) -> MagicMock:
    return _make_proc(json.dumps({"labels": [{"name": n} for n in names]}))


def _label_names_proc(*names: str) -> MagicMock:
    return _make_proc(json.dumps([[{"name": n, "color": "", "description": ""} for n in names]]))


# ---------------------------------------------------------------------------
# _load_label_names
# ---------------------------------------------------------------------------


def test_load_label_names_missing_file(tmp_path):
    with patch.object(server, "_LABELS_JSON", tmp_path / "does-not-exist.json"):
        with pytest.raises(OSError):
            _load_label_names()


def test_load_label_names_corrupt_json(tmp_path):
    bad_file = tmp_path / "labels.json"
    bad_file.write_text("{not valid json")
    with patch.object(server, "_LABELS_JSON", bad_file):
        with pytest.raises(json.JSONDecodeError):
            _load_label_names()


def test_load_label_names_missing_name_key(tmp_path):
    bad_file = tmp_path / "labels.json"
    bad_file.write_text(json.dumps({"labels": [{"color": "fff"}]}))
    with patch.object(server, "_LABELS_JSON", bad_file):
        with pytest.raises(KeyError):
            _load_label_names()


def test_load_label_names_valid_file(tmp_path):
    good_file = tmp_path / "labels.json"
    good_file.write_text(json.dumps({"labels": [{"name": "bug"}, {"name": "type:bug"}]}))
    with patch.object(server, "_LABELS_JSON", good_file):
        assert _load_label_names() == ["bug", "type:bug"]


def test_known_labels_are_loaded_once_at_import_time(tmp_path):
    """_KNOWN_LABELS/_LABEL_DESCRIPTION are computed once at import, from the
    labels.json on disk at that time. Changing the file afterwards has no
    effect on the module-level cache -- this is intentional (labels.json only
    changes via a separate PR, never mid-process), so _load_label_names is not
    re-run on every tool call.
    """
    original = list(server._KNOWN_LABELS)
    good_file = tmp_path / "labels.json"
    good_file.write_text(json.dumps({"labels": [{"name": "brand-new-label"}]}))
    with patch.object(server, "_LABELS_JSON", good_file):
        # A fresh call reflects the new file...
        assert _load_label_names() == ["brand-new-label"]
        # ...but the cached module-level constants computed at import do not.
        assert server._KNOWN_LABELS == original


# ---------------------------------------------------------------------------
# view_issue
# ---------------------------------------------------------------------------


def test_view_issue_returns_flat_json():
    with patch("server.fetch_issue.fetch_issue") as mock_fetch:
        mock_fetch.return_value = fetch_issue.Issue(
            number=1,
            title="T",
            body="B",
            state="OPEN",
            labels=["bug"],
            comments=[],
        )
        result = view_issue(issue_number=1)

    data = json.loads(result)
    assert data["number"] == 1
    assert data["labels"] == ["bug"]
    assert "nodes" not in str(data)


# ---------------------------------------------------------------------------
# list_issues
# ---------------------------------------------------------------------------


def test_list_issues_no_label():
    with patch("server.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc(
            '[[{"number":1,"title":"T","labels":[],"state":"open"}]]'
        )
        with patch.object(server, "_REPO", "owner/repo"):
            result = list_issues()

    cmd = mock_run.call_args[0][0]
    assert not any("labels=" in arg for arg in cmd)
    assert json.loads(result) == [{"number": 1, "title": "T", "labels": [], "state": "OPEN"}]


def test_list_issues_with_label():
    with patch("server.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc("[[]]")
        with patch.object(server, "_REPO", "owner/repo"):
            list_issues(label="bug")

    cmd = mock_run.call_args[0][0]
    assert any(arg.endswith("&labels=bug") for arg in cmd)


def test_list_issues_surfaces_gh_error():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_failure("gh: repository not found")
        with patch.object(server, "_REPO", "owner/repo"):
            with pytest.raises(GhCommandError, match="repository not found"):
                list_issues()


# ---------------------------------------------------------------------------
# comment_issue
# ---------------------------------------------------------------------------


def test_comment_issue():
    with patch("server.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc("https://github.com/.../42#issuecomment-1")
        with patch.object(server, "_REPO", "owner/repo"):
            result = comment_issue(issue_number=42, body="Hello")

    cmd = mock_run.call_args[0][0]
    assert "gh" in cmd
    assert "issue" in cmd
    assert "comment" in cmd
    assert "42" in cmd
    assert "--body" in cmd
    assert "Hello" in cmd


def test_comment_issue_surfaces_gh_error():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_failure("gh: issue not found")
        with patch.object(server, "_REPO", "owner/repo"):
            with pytest.raises(GhCommandError, match="issue not found"):
                comment_issue(issue_number=42, body="Hello")


# ---------------------------------------------------------------------------
# edit_issue
# ---------------------------------------------------------------------------


def test_edit_issue_body_only():
    with patch("server.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc()
        with patch.object(server, "_REPO", "owner/repo"):
            edit_issue(issue_number=5, body="New body\n## Header\nContent")

    cmd = mock_run.call_args[0][0]
    assert "edit" in cmd
    assert "--body" in cmd
    assert "5" in cmd
    assert "--title" not in cmd


def test_edit_issue_with_title():
    with patch("server.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc()
        with patch.object(server, "_REPO", "owner/repo"):
            edit_issue(issue_number=5, body="Updated body content here", title="New title")

    cmd = mock_run.call_args[0][0]
    assert "--body" in cmd
    assert "--title" in cmd
    assert "New title" in cmd


def test_edit_issue_rejects_multiline_title():
    with pytest.raises(InvalidInputError, match="single line"):
        edit_issue(issue_number=5, body="Some body content here", title="Line one\nLine two")


def test_edit_issue_surfaces_gh_error():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_failure("gh: issue not found")
        with patch.object(server, "_REPO", "owner/repo"):
            with pytest.raises(GhCommandError, match="issue not found"):
                edit_issue(issue_number=5, body="New body content here")


# ---------------------------------------------------------------------------
# edit_issue_labels
# ---------------------------------------------------------------------------


def _mock_label_list(mock_run: MagicMock, labels: list[str]) -> None:
    mock_run.return_value = _make_proc("\n".join(labels))


def test_edit_issue_labels_add():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = [
            _label_names_proc("bug", "priority:high", "status:ready"),  # label list
            _issue_labels_proc(),  # current issue labels
            _make_proc(),  # issue edit
        ]
        with patch.object(server, "_REPO", "owner/repo"):
            edit_issue_labels(issue_number=7, add_labels=["bug"])

    edit_call = mock_run.call_args_list[2][0][0]
    assert "--add-label" in edit_call
    assert "bug" in edit_call


def test_edit_issue_labels_remove():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = [
            _label_names_proc("bug", "priority:high"),
            _issue_labels_proc("bug"),
            _make_proc(),
        ]
        with patch.object(server, "_REPO", "owner/repo"):
            edit_issue_labels(issue_number=7, remove_labels=["bug"])

    edit_call = mock_run.call_args_list[2][0][0]
    assert "--remove-label" in edit_call


def test_edit_issue_labels_rejects_unknown():
    with patch("server.subprocess.run") as mock_run:
        mock_run.return_value = _label_names_proc("bug")
        with patch.object(server, "_REPO", "owner/repo"):
            with pytest.raises(InvalidInputError, match="don't exist"):
                edit_issue_labels(issue_number=7, add_labels=["no-such-label"])


def test_edit_issue_labels_noop():
    result = edit_issue_labels(issue_number=7)
    assert result == "Nothing to do"


def test_edit_issue_labels_surfaces_gh_error_on_label_list():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_failure("gh: not authenticated")
        with patch.object(server, "_REPO", "owner/repo"):
            with pytest.raises(GhCommandError, match="not authenticated"):
                edit_issue_labels(issue_number=7, add_labels=["bug"])


def test_edit_issue_labels_surfaces_gh_error_on_edit():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = [
            _label_names_proc("bug"),  # label list succeeds
            _issue_labels_proc(),
            _gh_failure("gh: issue not found"),  # edit fails
        ]
        with patch.object(server, "_REPO", "owner/repo"):
            with pytest.raises(GhCommandError, match="issue not found"):
                edit_issue_labels(issue_number=7, add_labels=["bug"])


# ---------------------------------------------------------------------------
# comment_pr
# ---------------------------------------------------------------------------


def test_comment_pr():
    with patch("server.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc("https://...")
        with patch.object(server, "_REPO", "owner/repo"):
            comment_pr(pr_number=99, body="LGTM")

    cmd = mock_run.call_args[0][0]
    assert "pr" in cmd
    assert "comment" in cmd
    assert "99" in cmd
    assert "--body" in cmd


def test_comment_pr_surfaces_gh_error():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_failure("gh: pull request not found")
        with patch.object(server, "_REPO", "owner/repo"):
            with pytest.raises(GhCommandError, match="pull request not found"):
                comment_pr(pr_number=99, body="LGTM")


# ---------------------------------------------------------------------------
# open_pr
# ---------------------------------------------------------------------------


def test_open_pr_appends_closes():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = [
            _make_proc("feat/x"),  # git rev-parse --abbrev-ref HEAD
            _make_proc('{"default_branch": "main"}'),  # gh api repos/...
            _make_proc("https://github.com/owner/repo/pull/1"),  # gh pr create
        ]
        with patch.object(server, "_REPO", "owner/repo"):
            with patch.object(server, "_WORKSPACE", "/workspace"):
                open_pr(issue_number=42, title="feat: add thing", body="Implements the thing")

    assert mock_run.call_args_list[0][1].get("cwd") == "/workspace"
    cmd = mock_run.call_args_list[2][0][0]
    assert cmd[cmd.index("--head") + 1] == "feat/x"
    assert cmd[cmd.index("--base") + 1] == "main"
    body = cmd[cmd.index("--body") + 1]
    assert "Closes #42" in body
    assert "Implements the thing" in body


def test_open_pr_rejects_detached_head():
    with patch("server.subprocess.run", return_value=_make_proc("HEAD")):
        with patch.object(server, "_REPO", "owner/repo"):
            with pytest.raises(GhCommandError, match="detached HEAD"):
                open_pr(issue_number=42, title="feat: add thing", body="Implements the thing")


def test_open_pr_surfaces_gh_error():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = [
            _make_proc("feat/x"),
            _make_proc('{"default_branch": "main"}'),
            _gh_failure("error creating pull request: No commits between 'main' and 'feat/x'"),
        ]
        with patch.object(server, "_REPO", "owner/repo"):
            with pytest.raises(GhCommandError, match="No commits between"):
                open_pr(issue_number=42, title="feat: add thing", body="Implements the thing")


# ---------------------------------------------------------------------------
# submit_pr_review
# ---------------------------------------------------------------------------


def test_submit_pr_review_approve():
    with patch("server.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc('{"id": 1}')
        with patch.object(server, "_REPO", "owner/repo"):
            submit_pr_review(pr_number=10, event="APPROVE", body="Looks good")

    cmd = mock_run.call_args[0][0]
    assert "POST" in cmd
    assert any("pulls/10/reviews" in arg for arg in cmd)
    payload = json.loads(mock_run.call_args[1]["input"])
    assert payload["event"] == "APPROVE"
    assert payload["body"] == "Looks good"
    assert payload["comments"] == []


def test_submit_pr_review_request_changes_with_comments():
    with patch("server.subprocess.run") as mock_run:
        mock_run.return_value = _make_proc('{"id": 2}')
        with patch.object(server, "_REPO", "owner/repo"):
            submit_pr_review(
                pr_number=10,
                event="REQUEST_CHANGES",
                body="Needs work here",
                comments=[InlineComment(path="foo.py", line=5, body="Fix this")],
            )

    payload = json.loads(mock_run.call_args[1]["input"])
    assert payload["event"] == "REQUEST_CHANGES"
    assert len(payload["comments"]) == 1
    assert payload["comments"][0] == {"path": "foo.py", "line": 5, "body": "Fix this"}


def test_submit_pr_review_rejects_bad_event():
    with pytest.raises(InvalidInputError, match="APPROVE or REQUEST_CHANGES"):
        submit_pr_review(pr_number=10, event="COMMENT", body="hi")


def test_submit_pr_review_surfaces_gh_error():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_failure("gh: validation failed")
        with patch.object(server, "_REPO", "owner/repo"):
            with pytest.raises(GhCommandError, match="validation failed"):
                submit_pr_review(pr_number=10, event="APPROVE", body="Looks good")


# ---------------------------------------------------------------------------
# push_branch
# ---------------------------------------------------------------------------


@pytest.fixture
def _default_branch():
    with patch("server.gh.default_branch", return_value="main") as m:
        yield m


def _git_seq(*stdout_values: str) -> list[MagicMock]:
    return [_make_proc(v) for v in stdout_values]


@pytest.mark.usefixtures("_default_branch")
def test_push_branch_squashes_and_pushes():
    seq = _git_seq(
        "feat/my-branch",   # rev-parse --abbrev-ref HEAD
        "",                 # fetch origin main
        "abc123",           # merge-base
        "def456",           # rev-parse HEAD
        "commit message",   # log -1
        "",                 # reset --soft
        "",                 # commit
        "file.py",          # diff-tree (no protected paths)
        "",                 # push
    )
    with patch("server.subprocess.run", side_effect=seq):
        result = push_branch()

    assert "feat/my-branch" in result


def test_push_branch_uses_the_repos_default_branch(_default_branch):
    _default_branch.return_value = "develop"
    seq = _git_seq("feat/x", "", "abc123", "def456", "msg", "", "", "file.py", "")
    with patch("server.subprocess.run", side_effect=seq) as run:
        push_branch()
    cmds = [c[0][0] for c in run.call_args_list]
    assert ["git", "fetch", "origin", "develop", "--quiet"] in cmds
    assert ["git", "merge-base", "origin/develop", "HEAD"] in cmds


@pytest.mark.usefixtures("_default_branch")
def test_push_branch_rejects_main():
    with patch("server.subprocess.run", return_value=_make_proc("main")):
        with pytest.raises(PushRefusedError, match="Refusing"):
            push_branch()


@pytest.mark.usefixtures("_default_branch")
def test_push_branch_rejects_no_commits():
    seq = _git_seq(
        "my-branch",  # branch name
        "",           # fetch
        "abc123",     # merge-base
        "abc123",     # HEAD == base => nothing to push
    )
    with patch("server.subprocess.run", side_effect=seq):
        with pytest.raises(PushRefusedError, match="nothing to push"):
            push_branch()


@pytest.mark.usefixtures("_default_branch")
def test_push_branch_rejects_protected_paths():
    seq = _git_seq(
        "my-branch",
        "",
        "abc123",
        "def456",
        "fix: update",
        "",
        "",
        ".github/workflows/ci.yml",  # protected path
    )
    with patch("server.subprocess.run", side_effect=seq):
        with pytest.raises(PushRefusedError, match="protected paths"):
            push_branch()


@pytest.mark.usefixtures("_default_branch")
def test_push_branch_surfaces_git_error():
    seq = [
        _make_proc("my-branch"),  # rev-parse --abbrev-ref HEAD
        _make_proc(returncode=1, stderr="fatal: unable to access origin"),  # fetch fails
    ]
    with patch("server.subprocess.run", side_effect=seq):
        with pytest.raises(GhCommandError, match="unable to access origin"):
            push_branch()


@pytest.mark.usefixtures("_default_branch")
def test_push_branch_rejects_scripts_protected_paths():
    seq = _git_seq(
        "my-branch",
        "",
        "abc123",
        "def456",
        "chore: update",
        "",
        "",
        ".github/workflows/code-pipeline.yml",
    )
    with patch("server.subprocess.run", side_effect=seq):
        with pytest.raises(PushRefusedError, match="protected paths"):
            push_branch()


# ---------------------------------------------------------------------------
# apply_refinement_outcome
# ---------------------------------------------------------------------------


def test_apply_refinement_outcome_refined():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = [_issue_labels_proc("status:needs-refinement"), _make_proc()]
        with patch.object(server, "_REPO", "owner/repo"):
            result = apply_refinement_outcome(
                issue_number=5, outcome="refined", type_label="type:coding-task"
            )

    cmd = mock_run.call_args_list[1][0][0]
    assert "--add-label" in cmd
    assert "status:refined" in cmd
    assert "type:coding-task" in cmd
    assert "--remove-label" in cmd
    assert "status:needs-refinement" in cmd
    assert "refined" in result


def test_apply_refinement_outcome_missing_type_label():
    with pytest.raises(InvalidInputError, match="type_label is required"):
        apply_refinement_outcome(issue_number=5, outcome="refined")


def test_apply_refinement_outcome_needs_attention():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = [_issue_labels_proc("status:needs-refinement"), _make_proc()]
        with patch.object(server, "_REPO", "owner/repo"):
            result = apply_refinement_outcome(issue_number=5, outcome="needs-attention")

    cmd = mock_run.call_args_list[1][0][0]
    assert "--add-label" in cmd
    assert "status:needs-attention" in cmd
    assert "--remove-label" in cmd
    assert "status:needs-refinement" in cmd
    assert "status:refined" not in cmd
    assert "needs-attention" in result


def test_apply_refinement_outcome_invalid():
    with pytest.raises(InvalidInputError):
        apply_refinement_outcome(issue_number=5, outcome="done")


def test_apply_refinement_outcome_surfaces_gh_error():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_failure("gh: issue not found")
        with patch.object(server, "_REPO", "owner/repo"):
            with pytest.raises(GhCommandError, match="issue not found"):
                apply_refinement_outcome(issue_number=5, outcome="needs-attention")


# ---------------------------------------------------------------------------
# apply_estimation_outcome
# ---------------------------------------------------------------------------


def test_apply_estimation_outcome_estimated():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = [_issue_labels_proc("status:refined"), _make_proc()]
        with patch.object(server, "_REPO", "owner/repo"):
            result = apply_estimation_outcome(
                issue_number=7,
                outcome="estimated",
                blast_radius="Low",
                touch="Mid",
                human_involvement="Low",
                review_overhead="Low",
            )

    cmd = mock_run.call_args_list[1][0][0]
    assert "--add-label" in cmd
    assert "status:estimated" in cmd
    assert "size:S" in cmd
    assert "--remove-label" in cmd
    assert "status:refined" in cmd
    assert "estimated" in result
    assert "size:S" in result


def test_apply_estimation_outcome_needs_attention():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = [_issue_labels_proc("status:refined"), _make_proc()]
        with patch.object(server, "_REPO", "owner/repo"):
            result = apply_estimation_outcome(issue_number=7, outcome="needs-attention")

    cmd = mock_run.call_args_list[1][0][0]
    assert "--add-label" in cmd
    assert "status:needs-attention" in cmd
    assert "--remove-label" in cmd
    assert "status:refined" in cmd
    assert "needs-attention" in result


def test_apply_estimation_outcome_missing_scores():
    with pytest.raises(InvalidInputError):
        apply_estimation_outcome(issue_number=7, outcome="estimated")


def test_apply_estimation_outcome_rejects_bad_score():
    with pytest.raises(ValueError, match="Not a Low|Mid|High score"):
        apply_estimation_outcome(
            issue_number=7, outcome="estimated",
            blast_radius="Low", touch="Medium", human_involvement="Low", review_overhead="Low",
        )


def test_apply_estimation_outcome_invalid():
    with pytest.raises(InvalidInputError):
        apply_estimation_outcome(issue_number=7, outcome="done")


def test_apply_estimation_outcome_surfaces_gh_error():
    with patch("server.subprocess.run") as mock_run:
        mock_run.side_effect = _gh_failure("gh: issue not found")
        with patch.object(server, "_REPO", "owner/repo"):
            with pytest.raises(GhCommandError, match="issue not found"):
                apply_estimation_outcome(issue_number=7, outcome="needs-attention")
