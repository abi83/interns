"""The one executor for lifecycle Outcomes: label moves, the comment and the
coder fix-round dispatch. Comment wording lives here, keyed by comment kind,
so `lifecycle.decide` stays free of message text."""

from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from .. import gh
from . import labels
from .lifecycle import Comment, CommentKind, IssueChange, Outcome, Target


class Words(NamedTuple):
    """Run-specific text for comments. `detail` is the kind-specific free text:
    the red-check reason, the give-up note, the review cap or the failure
    details; `noun` names the failed job."""

    run_url: str
    server_url: str = ""
    detail: str = ""
    noun: str = ""


class _Where(NamedTuple):
    repo: str
    pr: int | None
    issue: int | None
    words: Words


def _approved(w: _Where) -> str:
    return (
        f"Reviewer approved [PR #{w.pr}]({w.words.server_url}/{w.repo}/pull/{w.pr}) — awaiting owner merge. "
        f"Run: {w.words.run_url}"
    )


def _fix_loop_exhausted(w: _Where) -> str:
    return (
        "Second review still requests changes — the automatic fix round didn't converge. "
        f"Escalating to a human. See the run: {w.words.run_url}"
    )


def _changes_requested_no_issue(w: _Where) -> str:
    return (
        "Changes requested but this PR has no linked issue — can't dispatch a coder fix round "
        f"automatically. See the run: {w.words.run_url}"
    )


def _no_verdict(w: _Where) -> str:
    return (
        "Review run completed without submitting a recognized verdict — likely stopped partway through. "
        f"See the run: {w.words.run_url}"
    )


def _red_checks(w: _Where) -> str:
    return (
        f"PR checks are not green ({w.words.detail}) — the reviewer won't run, so this is sent straight to a "
        "human rather than retried. The coder can only verify its work through your Makefile: make sure "
        "it has real `setup`, `test` and `build` targets (stubs are skipped), otherwise the coder "
        "cannot catch failures before pushing. "
        f"Run: {w.words.run_url}"
    )


def _review_cap_reached(w: _Where) -> str:
    return f"Automatic review limit ({w.words.detail}) reached — further review is manual. Run: {w.words.run_url}"


def _coder_gave_up(w: _Where) -> str:
    return (
        "The coder fix round declined this task and set `status:needs-attention` "
        "— it was not handed back to the reviewer.\n\n"
        f"{w.words.detail}\n\n"
        f"Run: {w.words.run_url}"
    )


def _coder_no_pr(w: _Where) -> str:
    return (
        "Coder run completed without leaving an open PR referencing this "
        "issue — likely stopped for clarification or partway through. "
        f"See the run: {w.words.run_url}"
    )


def _job_failed(w: _Where) -> str:
    return f"Automated {w.words.noun} failed. See the run: {w.words.run_url}{w.words.detail}"


def _fix_round_failed(w: _Where) -> str:
    return (
        "Automated fix round failed — issue set to `status:needs-attention`. "
        "Re-dispatch once the cause is addressed: `gh workflow run code-pipeline.yml "
        f"-f phase=coder -f issue_number={w.issue} -f fix_round=true`. Run: {w.words.run_url}{w.words.detail}"
    )


def _pr_closed_unmerged(w: _Where) -> str:
    return (
        f"[PR #{w.pr}]({w.words.server_url}/{w.repo}/pull/{w.pr}) was closed without merging — this issue needs a "
        f"human to decide whether to re-dispatch the coder (re-apply `status:ready`) or drop it. Run: {w.words.run_url}"
    )


MESSAGES: dict[CommentKind, Callable[[_Where], str]] = {
    CommentKind.APPROVED: _approved,
    CommentKind.FIX_LOOP_EXHAUSTED: _fix_loop_exhausted,
    CommentKind.CHANGES_REQUESTED_NO_ISSUE: _changes_requested_no_issue,
    CommentKind.NO_VERDICT: _no_verdict,
    CommentKind.RED_CHECKS: _red_checks,
    CommentKind.REVIEW_CAP_REACHED: _review_cap_reached,
    CommentKind.CODER_GAVE_UP: _coder_gave_up,
    CommentKind.CODER_NO_PR: _coder_no_pr,
    CommentKind.JOB_FAILED: _job_failed,
    CommentKind.FIX_ROUND_FAILED: _fix_round_failed,
    CommentKind.PR_CLOSED_UNMERGED: _pr_closed_unmerged,
}


def _post(where: _Where, comment: Comment) -> None:
    body = MESSAGES[comment.kind](where)
    if comment.target is Target.PR:
        if where.pr is None:
            raise ValueError(f"{comment.kind} comments on the PR but none was given")
        gh.pr_comment(where.repo, where.pr, body)
        return
    if where.issue is None:
        raise ValueError(f"{comment.kind} comments on the issue but none was given")
    gh.issue_comment(where.repo, where.issue, body)


def _change_issue(repo: str, issue: int | None, change: IssueChange) -> None:
    if change is IssueChange.UNCHANGED:
        return
    if issue is None:
        raise ValueError(f"issue change {change} requires an issue")
    if change is IssueChange.NEEDS_ATTENTION:
        labels.set_issue_status(repo, issue, labels.STATUS_NEEDS_ATTENTION)
        return
    labels.edit_issue_labels(repo, issue, remove=[labels.STATUS_IN_PROGRESS])


def apply(repo: str, outcome: Outcome, *, pr: int | None, issue: int | None, words: Words) -> None:
    if pr is not None:
        labels.set_pr_pipeline_label(repo, pr, outcome.pr_label)
    _change_issue(repo, issue, outcome.issue)
    if outcome.comment is not None:
        _post(_Where(repo, pr, issue, words), outcome.comment)
    if outcome.dispatch_fix_round:
        if issue is None:
            raise ValueError("a coder fix round requires an issue")
        # GITHUB_TOKEN label edits don't fire workflow runs (anti-recursion), so
        # dispatch the coder explicitly as a fix round.
        gh.dispatch_workflow(
            repo, "code-pipeline.yml", None,
            {"phase": "coder", "issue_number": str(issue), "fix_round": "true"},
        )
