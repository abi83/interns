import unittest
from unittest.mock import patch

from interns.domain import labels, lifecycle, lifecycle_apply
from interns.domain.lifecycle import Comment, CommentKind, Event, Facts, IssueChange, Outcome, Target
from interns.domain.lifecycle_apply import Words

REPO = "acme/widgets"
WORDS = Words(run_url="https://run", server_url="https://github.com", detail="DETAIL", noun="review")


def apply(outcome: Outcome, *, pr: int | None = 12, issue: int | None = 34):
    with patch("interns.domain.lifecycle_apply.labels.set_pr_pipeline_label") as set_pr, \
         patch("interns.domain.lifecycle_apply.labels.set_issue_status") as set_issue, \
         patch("interns.domain.lifecycle_apply.labels.edit_issue_labels") as edit_issue, \
         patch("interns.domain.lifecycle_apply.gh.pr_comment") as pr_comment, \
         patch("interns.domain.lifecycle_apply.gh.issue_comment") as issue_comment, \
         patch("interns.domain.lifecycle_apply.gh.dispatch_workflow") as dispatch:
        lifecycle_apply.apply(REPO, outcome, pr=pr, issue=issue, words=WORDS)
    return set_pr, set_issue, edit_issue, pr_comment, issue_comment, dispatch


class ApplyTests(unittest.TestCase):
    def test_sets_the_pr_label_and_issue_status(self):
        set_pr, set_issue, *_ = apply(Outcome(labels.PR_NEEDS_ATTENTION, IssueChange.NEEDS_ATTENTION, None, False))
        set_pr.assert_called_once_with(REPO, 12, labels.PR_NEEDS_ATTENTION)
        set_issue.assert_called_once_with(REPO, 34, labels.STATUS_NEEDS_ATTENTION)

    def test_a_none_pr_label_clears_the_pipeline_labels(self):
        set_pr, *_ = apply(Outcome(None, IssueChange.UNCHANGED, None, False))
        set_pr.assert_called_once_with(REPO, 12, None)

    def test_without_a_pr_the_pr_label_is_skipped(self):
        set_pr, *_ = apply(Outcome(labels.PR_NEEDS_ATTENTION, IssueChange.UNCHANGED, None, False), pr=None)
        set_pr.assert_not_called()

    def test_unchanged_issue_is_not_touched(self):
        _, set_issue, edit_issue, *_ = apply(Outcome(None, IssueChange.UNCHANGED, None, False))
        set_issue.assert_not_called()
        edit_issue.assert_not_called()

    def test_retire_in_progress_removes_only_that_label(self):
        _, set_issue, edit_issue, *_ = apply(Outcome(None, IssueChange.RETIRE_IN_PROGRESS, None, False))
        edit_issue.assert_called_once_with(REPO, 34, remove=[labels.STATUS_IN_PROGRESS])
        set_issue.assert_not_called()

    def test_an_issue_change_without_an_issue_raises(self):
        with self.assertRaises(ValueError):
            apply(Outcome(None, IssueChange.NEEDS_ATTENTION, None, False), issue=None)

    def test_pr_comment_goes_to_the_pr(self):
        outcome = Outcome(None, IssueChange.UNCHANGED, Comment(CommentKind.NO_VERDICT, Target.PR), False)
        *_, pr_comment, issue_comment, _ = apply(outcome)
        pr_comment.assert_called_once()
        issue_comment.assert_not_called()
        self.assertEqual(pr_comment.call_args.args[:2], (REPO, 12))

    def test_issue_comment_goes_to_the_issue(self):
        outcome = Outcome(None, IssueChange.UNCHANGED, Comment(CommentKind.CODER_NO_PR, Target.ISSUE), False)
        *_, pr_comment, issue_comment, _ = apply(outcome)
        issue_comment.assert_called_once()
        pr_comment.assert_not_called()
        self.assertEqual(issue_comment.call_args.args[:2], (REPO, 34))

    def test_a_comment_without_its_target_raises(self):
        on_pr = Outcome(None, IssueChange.UNCHANGED, Comment(CommentKind.NO_VERDICT, Target.PR), False)
        on_issue = Outcome(None, IssueChange.UNCHANGED, Comment(CommentKind.CODER_NO_PR, Target.ISSUE), False)
        with self.assertRaises(ValueError):
            apply(on_pr, pr=None)
        with self.assertRaises(ValueError):
            apply(on_issue, issue=None)

    def test_dispatches_the_coder_fix_round(self):
        *_, dispatch = apply(Outcome(labels.PR_CODING, IssueChange.UNCHANGED, None, True))
        dispatch.assert_called_once_with(
            REPO, "code-pipeline.yml", None, {"phase": "coder", "issue_number": "34", "fix_round": "true"}
        )

    def test_dispatch_without_an_issue_raises(self):
        with self.assertRaises(ValueError):
            apply(Outcome(labels.PR_CODING, IssueChange.UNCHANGED, None, True), issue=None)


class MessageTests(unittest.TestCase):
    def test_every_comment_kind_has_a_message(self):
        self.assertEqual(set(lifecycle_apply.MESSAGES), set(CommentKind))

    def test_every_message_links_the_run(self):
        where = lifecycle_apply._Where(REPO, 12, 34, WORDS)
        for kind, render in lifecycle_apply.MESSAGES.items():
            with self.subTest(kind=kind):
                self.assertIn("https://run", render(where))

    def test_approved_links_the_pr(self):
        body = lifecycle_apply.MESSAGES[CommentKind.APPROVED](lifecycle_apply._Where(REPO, 12, 34, WORDS))
        self.assertIn("[PR #12](https://github.com/acme/widgets/pull/12)", body)

    def test_every_scenario_applies(self):
        for scenario in lifecycle.SCENARIOS:
            outcome = lifecycle.decide(scenario.event, scenario.facts)
            with self.subTest(scenario=scenario.name):
                apply(
                    outcome,
                    pr=12 if scenario.facts.has_pr else None,
                    issue=34 if scenario.facts.has_issue else None,
                )

    def test_fix_round_failure_names_the_redispatch_command(self):
        outcome = lifecycle.decide(Event.JOB_CRASHED_FIX_ROUND, Facts(True, True))
        *_, issue_comment, _ = apply(outcome)
        self.assertIn("-f issue_number=34 -f fix_round=true", issue_comment.call_args.args[2])


if __name__ == "__main__":
    unittest.main()
