import unittest

from interns.domain import labels
from interns.domain.lifecycle import (
    SCENARIOS,
    Comment,
    CommentKind,
    Event,
    Facts,
    IssueChange,
    Outcome,
    Target,
    decide,
)

WITH_ISSUE = Facts(has_issue=True, has_pr=True)
NO_ISSUE = Facts(has_issue=False, has_pr=True)
NO_PR = Facts(has_issue=True, has_pr=False)


class DecideTests(unittest.TestCase):
    def test_coder_handoff_hands_the_pr_to_the_reviewer(self):
        self.assertEqual(
            decide(Event.CODER_HANDOFF, WITH_ISSUE),
            Outcome(labels.PR_IN_REVIEW, IssueChange.UNCHANGED, None, False),
        )

    def test_coder_no_pr_flags_the_issue(self):
        self.assertEqual(
            decide(Event.CODER_NO_PR, NO_PR),
            Outcome(None, IssueChange.NEEDS_ATTENTION, Comment(CommentKind.CODER_NO_PR, Target.ISSUE), False),
        )

    def test_coder_gave_up_clears_the_pr_label_and_flags_the_issue(self):
        self.assertEqual(
            decide(Event.CODER_GAVE_UP, WITH_ISSUE),
            Outcome(None, IssueChange.NEEDS_ATTENTION, Comment(CommentKind.CODER_GAVE_UP, Target.ISSUE), False),
        )

    def test_approved_clears_the_pr_label_and_tells_the_issue(self):
        self.assertEqual(
            decide(Event.APPROVED, WITH_ISSUE),
            Outcome(None, IssueChange.UNCHANGED, Comment(CommentKind.APPROVED, Target.ISSUE), False),
        )

    def test_approved_without_an_issue_is_silent(self):
        self.assertEqual(decide(Event.APPROVED, NO_ISSUE), Outcome(None, IssueChange.UNCHANGED, None, False))

    def test_changes_requested_within_the_cap_dispatches_a_fix_round(self):
        self.assertEqual(
            decide(Event.CHANGES_REQUESTED, Facts(True, True, fix_rounds=1, max_fix_rounds=1)),
            Outcome(labels.PR_CODING, IssueChange.UNCHANGED, None, True),
        )

    def test_changes_requested_past_the_cap_escalates_pr_and_issue(self):
        self.assertEqual(
            decide(Event.CHANGES_REQUESTED, Facts(True, True, fix_rounds=2, max_fix_rounds=1)),
            Outcome(
                labels.PR_NEEDS_ATTENTION,
                IssueChange.NEEDS_ATTENTION,
                Comment(CommentKind.FIX_LOOP_EXHAUSTED, Target.PR),
                False,
            ),
        )

    def test_changes_requested_past_the_cap_without_an_issue_escalates_only_the_pr(self):
        outcome = decide(Event.CHANGES_REQUESTED, Facts(False, True, fix_rounds=2, max_fix_rounds=1))
        self.assertEqual(outcome.pr_label, labels.PR_NEEDS_ATTENTION)
        self.assertEqual(outcome.issue, IssueChange.UNCHANGED)

    def test_changes_requested_without_an_issue_cannot_dispatch(self):
        self.assertEqual(
            decide(Event.CHANGES_REQUESTED, Facts(False, True, fix_rounds=1, max_fix_rounds=1)),
            Outcome(None, IssueChange.UNCHANGED, Comment(CommentKind.CHANGES_REQUESTED_NO_ISSUE, Target.PR), False),
        )

    def test_no_verdict_escalates_pr_and_issue(self):
        self.assertEqual(
            decide(Event.NO_VERDICT, WITH_ISSUE),
            Outcome(labels.PR_NEEDS_ATTENTION, IssueChange.NEEDS_ATTENTION, Comment(CommentKind.NO_VERDICT, Target.PR), False),
        )

    def test_no_verdict_without_an_issue_escalates_only_the_pr(self):
        self.assertEqual(decide(Event.NO_VERDICT, NO_ISSUE).issue, IssueChange.UNCHANGED)

    def test_red_checks_escalate_the_pr_only(self):
        self.assertEqual(
            decide(Event.RED_CHECKS, WITH_ISSUE),
            Outcome(labels.PR_NEEDS_ATTENTION, IssueChange.UNCHANGED, Comment(CommentKind.RED_CHECKS, Target.PR), False),
        )

    def test_review_cap_escalates_the_pr_only(self):
        self.assertEqual(
            decide(Event.REVIEW_CAP_REACHED, WITH_ISSUE),
            Outcome(
                labels.PR_NEEDS_ATTENTION, IssueChange.UNCHANGED, Comment(CommentKind.REVIEW_CAP_REACHED, Target.PR), False
            ),
        )

    def test_job_crash_escalates_pr_and_issue_and_comments_on_the_pr(self):
        self.assertEqual(
            decide(Event.JOB_CRASHED, WITH_ISSUE),
            Outcome(labels.PR_NEEDS_ATTENTION, IssueChange.NEEDS_ATTENTION, Comment(CommentKind.JOB_FAILED, Target.PR), False),
        )

    def test_job_crash_without_a_pr_comments_on_the_issue(self):
        self.assertEqual(decide(Event.JOB_CRASHED, NO_PR).comment, Comment(CommentKind.JOB_FAILED, Target.ISSUE))

    def test_job_crash_without_an_issue_escalates_only_the_pr(self):
        self.assertEqual(decide(Event.JOB_CRASHED, NO_ISSUE).issue, IssueChange.UNCHANGED)

    def test_job_crash_needs_an_issue_or_a_pr(self):
        with self.assertRaises(ValueError):
            decide(Event.JOB_CRASHED, Facts(False, False))

    def test_fix_round_crash_clears_the_pr_label_and_flags_the_issue(self):
        self.assertEqual(
            decide(Event.JOB_CRASHED_FIX_ROUND, WITH_ISSUE),
            Outcome(None, IssueChange.NEEDS_ATTENTION, Comment(CommentKind.FIX_ROUND_FAILED, Target.ISSUE), False),
        )

    def test_merged_pr_retires_the_issue_run_label(self):
        self.assertEqual(
            decide(Event.PR_CLOSED_MERGED, WITH_ISSUE),
            Outcome(None, IssueChange.RETIRE_IN_PROGRESS, None, False),
        )

    def test_merged_pr_without_an_issue_only_clears_the_pr_label(self):
        self.assertEqual(decide(Event.PR_CLOSED_MERGED, NO_ISSUE), Outcome(None, IssueChange.UNCHANGED, None, False))

    def test_unmerged_close_hands_the_issue_to_a_human(self):
        self.assertEqual(
            decide(Event.PR_CLOSED_UNMERGED, WITH_ISSUE),
            Outcome(None, IssueChange.NEEDS_ATTENTION, Comment(CommentKind.PR_CLOSED_UNMERGED, Target.ISSUE), False),
        )

    def test_unmerged_close_without_an_issue_only_clears_the_pr_label(self):
        self.assertEqual(decide(Event.PR_CLOSED_UNMERGED, NO_ISSUE), Outcome(None, IssueChange.UNCHANGED, None, False))

    def test_events_missing_their_required_subject_raise(self):
        for event, facts in [
            (Event.CODER_HANDOFF, NO_PR),
            (Event.CODER_NO_PR, NO_ISSUE),
            (Event.CODER_GAVE_UP, NO_ISSUE),
            (Event.APPROVED, NO_PR),
            (Event.CHANGES_REQUESTED, NO_PR),
            (Event.NO_VERDICT, NO_PR),
            (Event.RED_CHECKS, NO_PR),
            (Event.REVIEW_CAP_REACHED, NO_PR),
        ]:
            with self.subTest(event=event), self.assertRaises(ValueError):
                decide(event, facts)

    def test_every_event_has_a_scenario(self):
        self.assertEqual({s.event for s in SCENARIOS}, set(Event))

    def test_every_scenario_decides(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.name):
                decide(scenario.event, scenario.facts)


if __name__ == "__main__":
    unittest.main()
