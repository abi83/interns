"""Tests for gh-issues MCP server (dispatch layer only).

Business-logic tests for push_branch, pr_open_for_issue, issue_edit_validated,
edit_issue_labels_validated, apply_refinement, and apply_estimation live in
pipeline/tests/ and tests/contract/test_mcp_contract.py.
"""

import json
from unittest.mock import patch

import pytest

import server
from interns.steps import fetch_issue
from server import (
    GhCommandError,
    InlineComment,
    InvalidInputError,
    PushRefusedError,
    _load_label_names,
    apply_estimation_outcome,
    apply_refinement_outcome,
    edit_issue,
    edit_issue_labels,
    open_pr,
    push_branch,
    submit_pr_review,
    view_issue,
)

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
    original = list(server._KNOWN_LABELS)
    good_file = tmp_path / "labels.json"
    good_file.write_text(json.dumps({"labels": [{"name": "brand-new-label"}]}))
    with patch.object(server, "_LABELS_JSON", good_file):
        assert _load_label_names() == ["brand-new-label"]
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
# edit_issue — dispatches to gh.issue_edit_validated
# ---------------------------------------------------------------------------


def test_edit_issue_dispatches_to_pipeline():
    with patch("server.gh.issue_edit_validated", return_value="Updated body on issue #5") as mock:
        with patch.object(server, "_REPO", "owner/repo"):
            result = edit_issue(issue_number=5, body="New body here", title="New title")
    mock.assert_called_once_with("owner/repo", 5, body="New body here", title="New title")
    assert result == "Updated body on issue #5"


def test_edit_issue_rejects_multiline_title():
    with patch("server.gh.issue_edit_validated", side_effect=InvalidInputError("Title must be a single line")):
        with pytest.raises(InvalidInputError, match="single line"):
            edit_issue(issue_number=5, body="Some body content here", title="Line one\nLine two")


# ---------------------------------------------------------------------------
# edit_issue_labels — dispatches to labels.edit_issue_labels_validated
# ---------------------------------------------------------------------------


def test_edit_issue_labels_dispatches_to_pipeline():
    with patch("server.labels.edit_issue_labels_validated", return_value="Added: bug") as mock:
        with patch.object(server, "_REPO", "owner/repo"):
            result = edit_issue_labels(issue_number=7, add_labels=["bug"])
    mock.assert_called_once_with("owner/repo", 7, add=["bug"], remove=None)
    assert result == "Added: bug"


def test_edit_issue_labels_noop():
    with patch("server.labels.edit_issue_labels_validated", return_value="Nothing to do") as mock:
        with patch.object(server, "_REPO", "owner/repo"):
            result = edit_issue_labels(issue_number=7)
    mock.assert_called_once_with("owner/repo", 7, add=None, remove=None)
    assert result == "Nothing to do"


def test_edit_issue_labels_rejects_unknown():
    with patch("server.labels.edit_issue_labels_validated",
               side_effect=InvalidInputError("Labels don't exist, not added: no-such-label")):
        with pytest.raises(InvalidInputError, match="don't exist"):
            edit_issue_labels(issue_number=7, add_labels=["no-such-label"])


# ---------------------------------------------------------------------------
# open_pr — dispatches to push.pr_open_for_issue
# ---------------------------------------------------------------------------


def test_open_pr_dispatches_to_pipeline():
    with patch("server.push.pr_open_for_issue", return_value="https://github.com/owner/repo/pull/1") as mock:
        with patch.object(server, "_REPO", "owner/repo"):
            with patch.object(server, "_WORKSPACE", "/workspace"):
                result = open_pr(issue_number=42, title="feat: add thing", body="Implements the thing")
    mock.assert_called_once_with("owner/repo", "/workspace", 42, "feat: add thing", "Implements the thing")
    assert result == "https://github.com/owner/repo/pull/1"


def test_open_pr_rejects_detached_head():
    with patch("server.push.pr_open_for_issue",
               side_effect=GhCommandError("Cannot open a PR from a detached HEAD; check out a branch first")):
        with pytest.raises(GhCommandError, match="detached HEAD"):
            open_pr(issue_number=42, title="feat: add thing", body="Implements the thing")


# ---------------------------------------------------------------------------
# submit_pr_review — dispatches to gh.pr_submit_review
# ---------------------------------------------------------------------------


def test_submit_pr_review_approve():
    with patch("server.gh.pr_submit_review", return_value={"id": 1}) as mock:
        with patch.object(server, "_REPO", "owner/repo"):
            result = submit_pr_review(pr_number=10, event="APPROVE", body="Looks good")
    mock.assert_called_once_with("owner/repo", 10, "APPROVE", "Looks good", [])
    assert json.loads(result) == {"id": 1}


def test_submit_pr_review_request_changes_with_comments():
    with patch("server.gh.pr_submit_review", return_value={"id": 2}) as mock:
        with patch.object(server, "_REPO", "owner/repo"):
            submit_pr_review(
                pr_number=10,
                event="REQUEST_CHANGES",
                body="Needs work here",
                comments=[InlineComment(path="foo.py", line=5, body="Fix this")],
            )
    _, _, _, _, comments_arg = mock.call_args[0]
    assert comments_arg == [{"path": "foo.py", "line": 5, "body": "Fix this"}]


def test_submit_pr_review_rejects_bad_event():
    with patch("server.gh.pr_submit_review",
               side_effect=InvalidInputError("event must be APPROVE or REQUEST_CHANGES")):
        with pytest.raises(InvalidInputError, match="APPROVE or REQUEST_CHANGES"):
            submit_pr_review(pr_number=10, event="COMMENT", body="hi")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# push_branch — dispatches to push.push_branch
# ---------------------------------------------------------------------------


def test_push_branch_dispatches_to_pipeline():
    with patch("server.push.push_branch", return_value="Branch 'feat/x' squashed and pushed to origin") as mock:
        with patch.object(server, "_REPO", "owner/repo"):
            with patch.object(server, "_WORKSPACE", "/workspace"):
                result = push_branch()
    mock.assert_called_once_with("owner/repo", "/workspace")
    assert "feat/x" in result


def test_push_branch_raises_push_refused():
    with patch("server.push.push_branch", side_effect=PushRefusedError("Refusing to push main directly")):
        with pytest.raises(PushRefusedError, match="Refusing"):
            push_branch()


# ---------------------------------------------------------------------------
# apply_refinement_outcome — dispatches to labels.apply_refinement
# ---------------------------------------------------------------------------


def test_apply_refinement_outcome_dispatches_to_pipeline():
    with patch("server.labels.apply_refinement", return_value="Refinement outcome 'refined' applied to issue #5") as mock:
        with patch.object(server, "_REPO", "owner/repo"):
            result = apply_refinement_outcome(
                issue_number=5, outcome="refined", type_label="type:coding-task"
            )
    mock.assert_called_once_with("owner/repo", 5, "refined", "type:coding-task")
    assert "refined" in result


def test_apply_refinement_outcome_missing_type_label():
    with patch("server.labels.apply_refinement",
               side_effect=InvalidInputError("type_label is required when outcome='refined'")):
        with pytest.raises(InvalidInputError, match="type_label is required"):
            apply_refinement_outcome(issue_number=5, outcome="refined")


# ---------------------------------------------------------------------------
# apply_estimation_outcome — dispatches to labels.apply_estimation
# ---------------------------------------------------------------------------


def test_apply_estimation_outcome_dispatches_to_pipeline():
    with patch("server.labels.apply_estimation",
               return_value="Estimation outcome 'estimated' applied to issue #7 (size:S)") as mock_labels:
        with patch("server.gh.issue_comment") as mock_comment:
            with patch.object(server, "_REPO", "owner/repo"):
                result = apply_estimation_outcome(
                    issue_number=7, outcome="estimated",
                    blast_radius="Low", blast_radius_reason="isolated change in src/ghost.ts",
                    touch="Mid", touch_reason="touches player.ts, ghost.ts, render.ts",
                    human_involvement="Low", human_involvement_reason="no manual steps",
                    review_overhead="Low", review_overhead_reason="single PR, existing patterns",
                )
    mock_labels.assert_called_once_with("owner/repo", 7, "estimated", "Low", "Mid", "Low", "Low")
    mock_comment.assert_called_once()
    body = mock_comment.call_args[0][2]
    assert "BLAST RADIUS: Low" in body
    assert "isolated change in src/ghost.ts" in body
    assert "estimated" in result


def test_apply_estimation_outcome_missing_scores():
    with pytest.raises(InvalidInputError):
        apply_estimation_outcome(issue_number=7, outcome="estimated")
