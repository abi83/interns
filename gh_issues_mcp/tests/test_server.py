"""Tests for gh-issues MCP server (dispatch layer only).

Business-logic tests for push_branch, pr_open_for_issue, issue_edit_validated,
set_issue_type, apply_refinement, and apply_estimation live in
tests/contract/test_mcp_contract.py.
"""

import asyncio
import importlib.util
import json
import pathlib
from unittest.mock import patch

import pytest
from mcp.server.mcpserver.exceptions import ToolError

import server
from interns.cli import MissingEnvError
from interns.domain.size import Estimation, Score
from interns.domain import issues, labels
from server import (
    GhCommandError,
    InlineComment,
    InvalidInputError,
    PushRefusedError,
    _TOOLS,
    _load_label_names,
    build_server,
    apply_estimation_outcome,
    apply_refinement_outcome,
    edit_issue,
    open_pr,
    push_branch,
    set_issue_type,
    submit_pr_review,
    view_issue,
    view_job_log,
    view_pr,
    view_pr_diff,
)


@pytest.fixture(autouse=True)
def github_env(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("GITHUB_WORKSPACE", "/workspace")


def test_load_label_names_missing_file(tmp_path):
    with patch.object(server, "_LABELS_JSON", tmp_path / "does-not-exist.json"), pytest.raises(OSError):
        _load_label_names()


def test_load_label_names_corrupt_json(tmp_path):
    bad_file = tmp_path / "labels.json"
    bad_file.write_text("{not valid json")
    with patch.object(server, "_LABELS_JSON", bad_file), pytest.raises(json.JSONDecodeError):
        _load_label_names()


def test_load_label_names_missing_name_key(tmp_path):
    bad_file = tmp_path / "labels.json"
    bad_file.write_text(json.dumps({"labels": [{"color": "fff"}]}))
    with patch.object(server, "_LABELS_JSON", bad_file), pytest.raises(KeyError):
        _load_label_names()


def test_load_label_names_valid_file(tmp_path):
    good_file = tmp_path / "labels.json"
    good_file.write_text(json.dumps({"labels": [{"name": "bug"}, {"name": "type:bug"}]}))
    with patch.object(server, "_LABELS_JSON", good_file):
        assert _load_label_names() == ["bug", "type:bug"]


def test_importing_server_has_no_side_effects(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY")
    monkeypatch.delenv("GITHUB_WORKSPACE")
    spec = importlib.util.spec_from_file_location("server_fresh", server.__file__)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    with patch.object(pathlib.Path, "read_text", side_effect=AssertionError("labels manifest read at import")):
        spec.loader.exec_module(module)


def test_list_issues_advertises_manifest_labels(tmp_path):
    manifest = tmp_path / "labels.json"
    manifest.write_text(json.dumps({"labels": [{"name": "brand-new-label"}]}))
    with patch.object(server, "_LABELS_JSON", manifest):
        tools = asyncio.run(build_server(["list_issues"]).list_tools())
    description = tools[0].input_schema["properties"]["label"]["description"]
    assert "brand-new-label" in description


@pytest.mark.parametrize("missing", ["GITHUB_REPOSITORY", "GITHUB_WORKSPACE"])
def test_build_server_requires_github_env(monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(MissingEnvError, match=missing):
        build_server(["view_issue"])


def test_tool_invocation_requires_repository(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY")
    with pytest.raises(MissingEnvError, match="GITHUB_REPOSITORY"):
        view_issue(issue_number=1)


def test_tool_invocation_requires_workspace(monkeypatch):
    monkeypatch.delenv("GITHUB_WORKSPACE")
    with pytest.raises(MissingEnvError, match="GITHUB_WORKSPACE"):
        push_branch()


def test_view_issue_returns_flat_json():
    with patch("server.issues.fetch_issue") as mock_fetch:
        mock_fetch.return_value = issues.Issue(
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


def test_view_issue_excludes_pipeline_comments():
    response = {
        "number": 1, "title": "T", "body": "B", "state": "OPEN",
        "labels": {"nodes": []},
        "comments": {"nodes": [
            {"author": {"login": "alice"}, "createdAt": "2024-01-01T00:00:00Z", "body": "Human"},
            {"author": {"login": "github-actions"}, "createdAt": "2024-01-02T00:00:00Z", "body": "Pipeline started"},
        ]},
        "parent": None,
        "subIssues": {"nodes": []}, "blockedBy": {"nodes": []}, "blocking": {"nodes": []},
    }
    with patch("interns.domain.issues.gh.issue_with_relations", return_value=response):
        data = json.loads(view_issue(issue_number=1))

    assert [c["body"] for c in data["comments"]] == ["Human"]


def test_edit_issue_dispatches_to_pipeline():
    with patch("server.gh.issue_edit_validated", return_value="Updated body on issue #5") as mock:
        result = edit_issue(issue_number=5, body="New body here", title="New title")
    mock.assert_called_once_with("owner/repo", 5, body="New body here", title="New title")
    assert result == "Updated body on issue #5"


def test_edit_issue_rejects_multiline_title():
    with patch("server.gh.issue_edit_validated", side_effect=InvalidInputError("Title must be a single line")), pytest.raises(InvalidInputError, match="single line"):
        edit_issue(issue_number=5, body="Some body content here", title="Line one\nLine two")


def test_set_issue_type_dispatches_to_pipeline():
    with patch("server.labels.set_issue_type", return_value="Issue #7 type set to type:bug") as mock:
        result = set_issue_type(issue_number=7, type_label="type:bug")
    mock.assert_called_once_with("owner/repo", 7, "type:bug")
    assert result == "Issue #7 type set to type:bug"


def test_set_issue_type_schema_only_admits_type_labels():
    (tool,) = asyncio.run(build_server(["set_issue_type"]).list_tools())
    schema = tool.input_schema
    assert schema["properties"]["type_label"]["$ref"] == "#/$defs/TypeLabel"
    assert schema["$defs"]["TypeLabel"]["enum"] == list(labels.TYPE_LABELS)
    assert sorted(schema["properties"]) == ["issue_number", "type_label"]


@pytest.mark.parametrize(
    ("tool_name", "enum_name", "allowed"),
    [
        ("apply_refinement_outcome", "RefinementOutcome", ["refined", "needs-attention"]),
        ("apply_estimation_outcome", "EstimationOutcome", ["estimated", "needs-attention"]),
    ],
)
def test_outcome_schema_admits_exactly_the_documented_values(tool_name, enum_name, allowed):
    (tool,) = asyncio.run(build_server([tool_name]).list_tools())
    schema = tool.input_schema
    assert schema["properties"]["outcome"]["$ref"] == f"#/$defs/{enum_name}"
    assert schema["$defs"][enum_name]["enum"] == allowed


def test_open_pr_dispatches_to_pipeline():
    with patch("server.push.pr_open_for_issue", return_value="https://github.com/owner/repo/pull/1") as mock:
        result = open_pr(issue_number=42, title="feat: add thing", body="Implements the thing")
    mock.assert_called_once_with("owner/repo", "/workspace", 42, "feat: add thing", "Implements the thing")
    assert result == "https://github.com/owner/repo/pull/1"


def test_open_pr_rejects_detached_head():
    with (
        patch("server.push.pr_open_for_issue",
                   side_effect=GhCommandError("Cannot open a PR from a detached HEAD; check out a branch first")),
        pytest.raises(GhCommandError, match="detached HEAD"),
    ):
        open_pr(issue_number=42, title="feat: add thing", body="Implements the thing")


def test_submit_pr_review_approve():
    with patch("server.gh.pr_submit_review", return_value={"id": 1}) as mock:
        result = submit_pr_review(pr_number=10, event="APPROVE", body="Looks good")
    mock.assert_called_once_with("owner/repo", 10, "APPROVE", "Looks good", [])
    assert json.loads(result) == {"id": 1}


def test_submit_pr_review_request_changes_with_comments():
    with patch("server.gh.pr_submit_review", return_value={"id": 2}) as mock:
        submit_pr_review(
            pr_number=10,
            event="REQUEST_CHANGES",
            body="Needs work here",
            comments=[InlineComment(path="foo.py", line=5, body="Fix this")],
        )
    _, _, _, _, comments_arg = mock.call_args[0]
    assert comments_arg == [{"path": "foo.py", "line": 5, "body": "Fix this"}]


def test_submit_pr_review_rejects_bad_event():
    with (
        patch("server.gh.pr_submit_review",
                   side_effect=InvalidInputError("event must be APPROVE or REQUEST_CHANGES")),
        pytest.raises(InvalidInputError, match="APPROVE or REQUEST_CHANGES"),
    ):
        submit_pr_review(pr_number=10, event="COMMENT", body="hi")  # type: ignore[arg-type]


def test_push_branch_dispatches_to_pipeline():
    with patch("server.push.push_branch", return_value="Branch 'feat/x' squashed and pushed to origin") as mock:
        result = push_branch()
    mock.assert_called_once_with("owner/repo", "/workspace")
    assert "feat/x" in result


def test_push_branch_raises_push_refused():
    with patch("server.push.push_branch", side_effect=PushRefusedError("Refusing to push main directly")), pytest.raises(PushRefusedError, match="Refusing"):
        push_branch()


def test_apply_refinement_outcome_dispatches_to_pipeline():
    with patch("server.labels.apply_refinement", return_value="Refinement outcome 'refined' applied to issue #5") as mock:
        result = apply_refinement_outcome(
            issue_number=5, outcome="refined", type_label="type:coding-task"
        )
    mock.assert_called_once_with("owner/repo", 5, "refined", "type:coding-task")
    assert "refined" in result


def test_apply_refinement_outcome_missing_type_label():
    with (
        patch("server.labels.apply_refinement",
                   side_effect=InvalidInputError("type_label is required when outcome='refined'")),
        pytest.raises(InvalidInputError, match="type_label is required"),
    ):
        apply_refinement_outcome(issue_number=5, outcome="refined")


def test_apply_estimation_outcome_dispatches_to_pipeline():
    estimation = Estimation(
        blast_radius=Score("Low", "isolated change in src/ghost.ts"),
        touch=Score("Mid", "touches player.ts, ghost.ts, render.ts"),
        human_involvement=Score("Low", "no manual steps"),
        review_overhead=Score("Low", "single PR, existing patterns"),
    )
    with patch("server.labels.apply_estimation",
               return_value="Estimation outcome 'estimated' applied to issue #7 (size:S)") as mock_labels:
        result = apply_estimation_outcome(issue_number=7, outcome="estimated", estimation=estimation)
    mock_labels.assert_called_once_with("owner/repo", 7, "estimated", estimation)
    assert "estimated" in result


def test_apply_estimation_outcome_missing_scores():
    with pytest.raises(InvalidInputError):
        apply_estimation_outcome(issue_number=7, outcome="estimated")


def _pr_comment(author, body, n=1):
    return {"author": {"login": author}, "createdAt": f"2024-01-{n:02d}T00:00:00Z", "body": body}


def test_view_pr_returns_title_body_and_human_comments():
    raw = {"number": 3, "title": "T", "body": "B", "comments": [_pr_comment("alice", "Human")]}
    with patch("server.gh.pr_view", return_value=raw) as mock_view:
        data = json.loads(view_pr(pr_number=3))
    mock_view.assert_called_once_with("owner/repo", 3, ["number", "title", "body", "comments"])
    assert (data["title"], data["body"], data["total_comments"]) == ("T", "B", 1)
    assert [c["body"] for c in data["comments"]] == ["Human"]


def test_view_pr_excludes_pipeline_comments():
    raw = {"number": 3, "title": "T", "body": "B", "comments": [
        _pr_comment("alice", "Human", 1),
        _pr_comment("github-actions", "Pipeline started", 2),
    ]}
    with patch("server.gh.pr_view", return_value=raw):
        data = json.loads(view_pr(pr_number=3))
    assert [c["body"] for c in data["comments"]] == ["Human"]
    assert data["total_comments"] == 1


def test_view_pr_keeps_only_the_last_five_comments():
    raw = {"number": 3, "title": "T", "body": "B", "comments": [_pr_comment("alice", f"c{n}", n) for n in range(1, 9)]}
    with patch("server.gh.pr_view", return_value=raw):
        data = json.loads(view_pr(pr_number=3))
    assert [c["body"] for c in data["comments"]] == ["c4", "c5", "c6", "c7", "c8"]
    assert data["total_comments"] == 8


def test_view_pr_diff_returns_raw_diff():
    with patch("server.gh.pr_diff", return_value="diff --git a/x b/x\n") as mock_diff:
        assert view_pr_diff(pr_number=3) == "diff --git a/x b/x\n"
    mock_diff.assert_called_once_with("owner/repo", 3)


def test_pr_checks_returns_json_array():
    checks = [{"name": "ci", "bucket": "pass", "link": "https://github.com/o/r/actions/runs/1/job/2"}]
    with patch("server.gh.pr_checks", return_value=checks):
        assert json.loads(server.pr_checks(pr_number=3)) == checks


def test_view_job_log_returns_short_log_whole():
    with patch("server.gh.job_log", return_value="ok\n") as mock_log:
        assert view_job_log(job_id=9) == "ok\n"
    mock_log.assert_called_once_with("owner/repo", 9)


def test_view_job_log_keeps_only_the_tail_of_a_long_log():
    log = "a" * server._JOB_LOG_LIMIT + "tail"
    with patch("server.gh.job_log", return_value=log):
        result = view_job_log(job_id=9)
    assert result.endswith("tail")
    assert result.startswith("[log truncated")
    assert len(result) < len(log) + 100


def test_view_pr_diff_surfaces_gh_failure_as_tool_error():
    with patch("server.gh.pr_diff", side_effect=GhCommandError("no such PR")), pytest.raises(ToolError, match="no such PR"):
        asyncio.run(build_server(["view_pr_diff"]).call_tool("view_pr_diff", {"pr_number": 99}))


def _exposed(tool_names):
    return {t.name for t in asyncio.run(build_server(tool_names).list_tools())}


def test_build_server_exposes_only_named_tools():
    assert _exposed(["view_issue", "comment_issue"]) == {"view_issue", "comment_issue"}


def test_build_server_can_expose_every_tool():
    assert _exposed(list(_TOOLS)) == set(_TOOLS)


def test_build_server_rejects_unknown_tool():
    with pytest.raises(ValueError, match="nope"):
        build_server(["view_issue", "nope"])


def test_build_server_rejects_empty_list():
    with pytest.raises(ValueError, match="INTERNS_MCP_TOOLS"):
        build_server([])


def _call(tool_name, arguments=None):
    return asyncio.run(build_server([tool_name]).call_tool(tool_name, arguments or {}))


@pytest.mark.parametrize("error_cls", [InvalidInputError, GhCommandError, PushRefusedError])
def test_anticipated_errors_surface_their_message(error_cls):
    with patch.object(server.push, "push_branch", side_effect=error_cls("actionable detail")), pytest.raises(ToolError, match="actionable detail"):
        _call("push_branch")


def test_unexpected_errors_stay_opaque():
    with patch.object(server.push, "push_branch", side_effect=RuntimeError("internal secret")), pytest.raises(ToolError) as exc_info:
        _call("push_branch")
    assert "internal secret" not in str(exc_info.value)
