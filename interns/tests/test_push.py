"""Unit tests for pipeline.push — push_branch and pr_open_for_issue."""

from unittest.mock import MagicMock, patch

import pytest

from interns.push import pr_open_for_issue, push_branch
from interns.gh import GhCommandError, InvalidInputError, PushRefusedError


REPO = "owner/repo"
WORKSPACE = "/workspace"


def _proc(stdout: str = "", returncode: int = 0, stderr: str = "") -> MagicMock:
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    m.stderr = stderr
    return m


def _git_seq(*stdout_values: str) -> list[MagicMock]:
    return [_proc(v) for v in stdout_values]


# ---------------------------------------------------------------------------
# push_branch
# ---------------------------------------------------------------------------


@patch("interns.push.default_branch", return_value="main")
def test_push_branch_squashes_and_pushes(_):
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
    with patch("interns.push.subprocess.run", side_effect=seq):
        result = push_branch(REPO, WORKSPACE)

    assert "feat/my-branch" in result


@patch("interns.push.default_branch", return_value="develop")
def test_push_branch_uses_repos_default_branch(_):
    seq = _git_seq("feat/x", "", "abc123", "def456", "msg", "", "", "file.py", "")
    with patch("interns.push.subprocess.run", side_effect=seq) as run:
        push_branch(REPO, WORKSPACE)
    cmds = [c[0][0] for c in run.call_args_list]
    assert ["git", "fetch", "origin", "develop", "--quiet"] in cmds
    assert ["git", "merge-base", "origin/develop", "HEAD"] in cmds


@patch("interns.push.default_branch", return_value="main")
def test_push_branch_rejects_main(_):
    with patch("interns.push.subprocess.run", return_value=_proc("main")):
        with pytest.raises(PushRefusedError, match="Refusing"):
            push_branch(REPO, WORKSPACE)


@patch("interns.push.default_branch", return_value="main")
def test_push_branch_rejects_master(_):
    with patch("interns.push.subprocess.run", return_value=_proc("master")):
        with pytest.raises(PushRefusedError, match="Refusing"):
            push_branch(REPO, WORKSPACE)


@patch("interns.push.default_branch", return_value="main")
def test_push_branch_rejects_no_commits(_):
    seq = _git_seq("my-branch", "", "abc123", "abc123")
    with patch("interns.push.subprocess.run", side_effect=seq):
        with pytest.raises(PushRefusedError, match="nothing to push"):
            push_branch(REPO, WORKSPACE)


@patch("interns.push.default_branch", return_value="main")
def test_push_branch_rejects_protected_workflow_path(_):
    # Sequence includes the rollback reset that undoes the squash before raising.
    seq = _git_seq("my-branch", "", "abc123", "def456", "fix: update", "", "", ".github/workflows/ci.yml", "")
    with patch("interns.push.subprocess.run", side_effect=seq):
        with pytest.raises(PushRefusedError, match="protected paths"):
            push_branch(REPO, WORKSPACE)


@patch("interns.push.default_branch", return_value="main")
def test_push_branch_rejects_protected_scripts_path(_):
    seq = _git_seq("my-branch", "", "abc123", "def456", "chore: update", "", "", ".github/scripts/foo.py", "")
    with patch("interns.push.subprocess.run", side_effect=seq):
        with pytest.raises(PushRefusedError, match="protected paths"):
            push_branch(REPO, WORKSPACE)


@patch("interns.push.default_branch", return_value="main")
def test_push_branch_surfaces_git_error(_):
    seq = [
        _proc("my-branch"),
        _proc(returncode=1, stderr="fatal: unable to access origin"),
    ]
    with patch("interns.push.subprocess.run", side_effect=seq):
        with pytest.raises(GhCommandError, match="unable to access origin"):
            push_branch(REPO, WORKSPACE)


@patch("interns.push.default_branch", return_value="main")
def test_push_branch_passes_workspace_as_cwd(_):
    seq = _git_seq("feat/x", "", "abc123", "def456", "msg", "", "", "file.py", "")
    with patch("interns.push.subprocess.run", side_effect=seq) as run:
        push_branch(REPO, WORKSPACE)
    for c in run.call_args_list:
        assert c[1].get("cwd") == WORKSPACE


# ---------------------------------------------------------------------------
# pr_open_for_issue
# ---------------------------------------------------------------------------


@patch("interns.push.default_branch", return_value="main")
@patch("interns.push.pr_create", return_value="https://github.com/owner/repo/pull/1")
def test_pr_open_for_issue_appends_closes(mock_create, _):
    with patch("interns.push.subprocess.run", return_value=_proc("feat/x")):
        result = pr_open_for_issue(REPO, WORKSPACE, 42, "feat: add thing", "Implements the thing")

    _, _, _, _, body = mock_create.call_args[0]
    assert "Closes #42" in body
    assert "Implements the thing" in body
    assert result == "https://github.com/owner/repo/pull/1"


@patch("interns.push.default_branch", return_value="main")
@patch("interns.push.pr_create", return_value="https://github.com/owner/repo/pull/1")
def test_pr_open_for_issue_uses_correct_head_and_base(mock_create, _):
    with patch("interns.push.subprocess.run", return_value=_proc("feat/x")):
        pr_open_for_issue(REPO, WORKSPACE, 42, "feat: add thing", "Body text here")

    repo_arg, head, base, _, _ = mock_create.call_args[0]
    assert head == "feat/x"
    assert base == "main"
    assert repo_arg == REPO


def test_pr_open_for_issue_rejects_detached_head():
    with patch("interns.push.subprocess.run", return_value=_proc("HEAD")):
        with pytest.raises(GhCommandError, match="detached HEAD"):
            pr_open_for_issue(REPO, WORKSPACE, 42, "feat: add thing", "Body text here")


def test_pr_open_for_issue_rejects_multiline_title():
    with pytest.raises(InvalidInputError, match="single line"):
        pr_open_for_issue(REPO, WORKSPACE, 42, "line one\nline two", "Body text here")
