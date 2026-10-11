"""save_draft_pr against real git repos (a bare origin and a clone); only gh is faked."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from interns.ctx import ActionsCtx
from interns.gh import PushRefusedError
from interns.steps import save_draft_pr

REPO = "owner/repo"
DRAFT_URL = "https://github.com/owner/repo/pull/9"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return result.stdout.strip()


@pytest.fixture
def work(tmp_path, monkeypatch):
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    clone = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(origin), str(clone))
    (clone / "README.md").write_text("hello\n")
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "init")
    git(clone, "push", "-q", "origin", "main")
    git(clone, "checkout", "-q", "-b", "feat/issue-7-thing")
    return clone


@pytest.fixture(autouse=True)
def fake_gh():
    with patch.object(save_draft_pr.gh, "pr_for_head", return_value=None) as for_head, \
         patch.object(save_draft_pr.gh, "default_branch", return_value="main"), \
         patch("interns.steps.push.default_branch", return_value="main"), \
         patch.object(save_draft_pr.gh, "pr_create", return_value=DRAFT_URL) as create:
        yield type("Gh", (), {"for_head": for_head, "create": create})


def save(work: Path) -> str | None:
    return save_draft_pr.save_draft_pr(REPO, str(work), 7, "feat: do the thing", "https://run/1")


def write(work: Path, rel: str, text: str = "x\n") -> None:
    path = work / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def pushed_files(work: Path) -> list[str]:
    return git(work, "diff", "--name-only", "origin/main", "origin/feat/issue-7-thing").splitlines()


def test_uncommitted_work_is_committed_pushed_and_opened_as_a_draft(work, fake_gh):
    write(work, "src/a.py")

    assert save(work) == DRAFT_URL

    assert pushed_files(work) == ["src/a.py"]
    assert git(work, "log", "-1", "--format=%s", "origin/feat/issue-7-thing") == "feat: do the thing"
    args, kwargs = fake_gh.create.call_args
    assert args[:4] == (REPO, "feat/issue-7-thing", "main", "feat: do the thing")
    assert kwargs == {"draft": True}


def test_body_says_unfinished_links_the_run_and_refs_rather_than_closes(work, fake_gh):
    write(work, "src/a.py")
    save(work)
    body = fake_gh.create.call_args[0][4]
    assert "Unfinished automated attempt" in body
    assert "https://run/1" in body
    assert body.endswith("Refs #7")
    assert "Closes" not in body


def test_pipeline_checkout_and_protected_paths_are_left_out(work):
    write(work, "src/a.py")
    write(work, ".interns/tool.py")
    write(work, ".github/workflows/ci.yml")
    write(work, ".github/scripts/run.sh")
    write(work, ".github/ISSUE_TEMPLATE/bug.md")

    save(work)

    assert pushed_files(work) == [".github/ISSUE_TEMPLATE/bug.md", "src/a.py"]


def test_commits_the_agent_already_made_collapse_into_one_commit_without_protected_paths(work):
    write(work, "src/a.py")
    write(work, ".github/workflows/ci.yml")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "wip 1")
    write(work, "src/b.py")
    git(work, "add", "-A")
    git(work, "commit", "-q", "-m", "wip 2")
    write(work, "src/c.py")

    save(work)

    assert pushed_files(work) == ["src/a.py", "src/b.py", "src/c.py"]
    assert git(work, "rev-list", "--count", "origin/main..origin/feat/issue-7-thing") == "1"


def test_nothing_changed_opens_nothing(work, fake_gh):
    assert save(work) is None
    fake_gh.create.assert_not_called()
    assert git(work, "ls-remote", "--heads", "origin", "feat/issue-7-thing") == ""


def test_only_excluded_changes_open_nothing(work, fake_gh):
    write(work, ".interns/tool.py")
    write(work, ".github/workflows/ci.yml")

    assert save(work) is None

    fake_gh.create.assert_not_called()
    assert git(work, "ls-remote", "--heads", "origin", "feat/issue-7-thing") == ""


def test_a_branch_that_already_has_an_open_pr_is_left_alone(work, fake_gh):
    fake_gh.for_head.return_value = {"number": 3, "url": "u", "isDraft": False}
    write(work, "src/a.py")

    assert save(work) is None

    fake_gh.create.assert_not_called()
    assert git(work, "ls-remote", "--heads", "origin", "feat/issue-7-thing") == ""


def test_refuses_to_save_the_default_branch(work):
    git(work, "checkout", "-q", "main")
    write(work, "src/a.py")
    with pytest.raises(PushRefusedError):
        save(work)


def test_resumed_branch_is_updated_not_duplicated(work, fake_gh):
    write(work, "src/a.py")
    save(work)
    git(work, "fetch", "-q", "origin")
    write(work, "src/b.py")
    fake_gh.for_head.return_value = None

    save(work)

    assert pushed_files(work) == ["src/a.py", "src/b.py"]


class TestDraftTitle:
    def test_prefixes_the_commit_type_hint(self):
        assert save_draft_pr.draft_title("feat:", "add a thing") == "feat: add a thing"

    def test_keeps_an_issue_title_that_is_already_conventional(self):
        assert save_draft_pr.draft_title("feat:", "fix(#56): add a thing") == "fix(#56): add a thing"


def test_main_writes_the_draft_url_output(work, tmp_path, monkeypatch):
    output = tmp_path / "out"
    output.write_bytes(b"")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    write(work, "src/a.py")
    ctx = ActionsCtx(repo=REPO, token="t", server_url="https://github.com", run_id="5", run_attempt=1,
                     workspace=str(work), event_name="issues", reviewer_bot="", step_summary="")

    assert save_draft_pr._main(ctx, ["--issue", "7", "--issue-title", "do it", "--commit-type-hint", "feat:"]) == 0

    assert output.read_text() == f"draft_pr_url={DRAFT_URL}\n"


def test_main_writes_no_output_when_nothing_was_saved(work, tmp_path, monkeypatch):
    output = tmp_path / "out"
    output.write_bytes(b"")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    ctx = ActionsCtx(repo=REPO, token="t", server_url="https://github.com", run_id="5", run_attempt=1,
                     workspace=str(work), event_name="issues", reviewer_bot="", step_summary="")

    assert save_draft_pr._main(ctx, ["--issue", "7", "--issue-title", "do it", "--commit-type-hint", "feat:"]) == 0

    assert output.read_text() == ""
