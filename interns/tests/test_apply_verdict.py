import unittest
from unittest.mock import patch

from interns.domain import labels, lifecycle
from interns.domain.verdict import Review, ReviewState
from interns.steps import apply_verdict

REVIEWER = "reviewer[bot]"


def review(state: ReviewState, commit_id: str = "headsha") -> Review:
    return Review(login=REVIEWER, state=state, commit_id=commit_id)


def run(reviews: list[Review], issue: int | None):
    with patch("interns.steps.apply_verdict.gh.pr_view", return_value={"headRefOid": "headsha"}), \
         patch("interns.steps.apply_verdict.verdict.reviews_by", return_value=reviews), \
         patch("interns.steps.apply_verdict.lifecycle_apply.apply") as apply:
        apply_verdict.apply_verdict("acme/widgets", 12, issue, REVIEWER, max_fix_rounds=1, server_url="https://github.com", run_url="run")
    apply.assert_called_once()
    return apply


class ApplyVerdictTests(unittest.TestCase):
    def test_approved_fires_the_approved_event(self):
        apply = run([review(ReviewState.APPROVED)], 34)
        self.assertEqual(apply.call_args.args[1], lifecycle.decide(lifecycle.Event.APPROVED, lifecycle.Facts(True, True)))
        self.assertEqual(apply.call_args.kwargs["pr"], 12)
        self.assertEqual(apply.call_args.kwargs["issue"], 34)
        self.assertEqual(apply.call_args.kwargs["words"].server_url, "https://github.com")

    def test_first_changes_requested_dispatches_a_fix_round(self):
        outcome = run([review(ReviewState.CHANGES_REQUESTED)], 34).call_args.args[1]
        self.assertEqual(outcome.pr_label, labels.PR_CODING)
        self.assertTrue(outcome.dispatch_fix_round)

    def test_second_changes_requested_exhausts_the_fix_loop(self):
        outcome = run([review(ReviewState.CHANGES_REQUESTED, "oldsha"), review(ReviewState.CHANGES_REQUESTED)], 34).call_args.args[1]
        self.assertEqual(outcome.pr_label, labels.PR_NEEDS_ATTENTION)
        self.assertFalse(outcome.dispatch_fix_round)

    def test_changes_requested_with_no_linked_issue_cannot_dispatch(self):
        outcome = run([review(ReviewState.CHANGES_REQUESTED)], None).call_args.args[1]
        self.assertFalse(outcome.dispatch_fix_round)
        self.assertEqual(outcome.comment.kind, lifecycle.CommentKind.CHANGES_REQUESTED_NO_ISSUE)

    def test_unrecognized_verdict_fires_no_verdict(self):
        outcome = run([review(ReviewState.COMMENTED)], 34).call_args.args[1]
        self.assertEqual(outcome, lifecycle.decide(lifecycle.Event.NO_VERDICT, lifecycle.Facts(True, True)))

    def test_stale_review_against_an_earlier_commit_fires_no_verdict(self):
        outcome = run([review(ReviewState.APPROVED, "oldsha")], 34).call_args.args[1]
        self.assertEqual(outcome, lifecycle.decide(lifecycle.Event.NO_VERDICT, lifecycle.Facts(True, True)))


if __name__ == "__main__":
    unittest.main()
