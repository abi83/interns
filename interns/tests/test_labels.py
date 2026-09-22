import unittest
from unittest.mock import patch

from interns import gh, labels


def _labels_response(names: list[str]) -> dict:
    return {"labels": [{"name": name} for name in names]}


class ReadLabelsTests(unittest.TestCase):
    def test_issue_labels(self):
        with patch("interns.gh.issue_view", return_value=_labels_response(["type:bug", "status:ready"])):
            self.assertEqual(labels.issue_labels("o/r", 7), ["type:bug", "status:ready"])

    def test_pr_labels(self):
        with patch("interns.gh.pr_view", return_value=_labels_response(["pr:in-review"])):
            self.assertEqual(labels.pr_labels("o/r", 3), ["pr:in-review"])


class SetIssueStatusTests(unittest.TestCase):
    def test_adds_target_and_removes_only_present_lifecycle_labels(self):
        with patch("interns.gh.issue_view", return_value=_labels_response(["type:bug", "status:in-progress"])), \
             patch("interns.gh.issue_edit") as mock_edit:
            labels.set_issue_status("o/r", 7, "status:needs-attention")
        mock_edit.assert_called_once_with(
            "o/r", 7, add_labels=["status:needs-attention"], remove_labels=["status:in-progress"]
        )

    def test_no_lifecycle_label_present_just_adds_target(self):
        with patch("interns.gh.issue_view", return_value=_labels_response(["status:needs-refinement"])), \
             patch("interns.gh.issue_edit") as mock_edit:
            labels.set_issue_status("o/r", 7, "status:needs-attention")
        mock_edit.assert_called_once_with("o/r", 7, add_labels=["status:needs-attention"], remove_labels=[])

    def test_target_already_present_is_a_noop(self):
        with patch("interns.gh.issue_view", return_value=_labels_response(["status:ready"])), \
             patch("interns.gh.issue_edit") as mock_edit:
            labels.set_issue_status("o/r", 7, "status:ready")
        mock_edit.assert_not_called()

    def test_a_failed_edit_does_not_raise(self):
        with patch("interns.gh.issue_view", return_value=_labels_response([])), \
             patch("interns.gh.issue_edit", side_effect=gh.GhCommandError("boom")):
            labels.set_issue_status("o/r", 7, "status:ready")  # does not raise


class TransitionTests(unittest.TestCase):
    def test_refined(self):
        self.assertEqual(
            labels.refined(labels.TYPE_BUG),
            labels.Transition(
                add=[labels.STATUS_REFINED, labels.TYPE_BUG],
                remove=[labels.STATUS_NEEDS_REFINEMENT, labels.STATUS_NEEDS_ATTENTION],
            ),
        )

    def test_estimated_adds_size_label(self):
        transition = labels.estimated("S")
        self.assertEqual(transition.add, [labels.STATUS_ESTIMATED, "size:S"])
        self.assertEqual(transition.remove, [labels.STATUS_REFINED, labels.STATUS_NEEDS_ATTENTION])
        self.assertEqual(labels.find_size_label(transition.add), "size:S")

    def test_needs_attention_transitions(self):
        self.assertEqual(labels.refinement_needs_attention().remove, [labels.STATUS_NEEDS_REFINEMENT])
        self.assertEqual(labels.estimation_needs_attention().remove, [labels.STATUS_REFINED])

    def test_find_size_label_none(self):
        self.assertIsNone(labels.find_size_label(["type:bug"]))


class ApplyTransitionTests(unittest.TestCase):
    def test_edits_only_what_changes(self):
        with patch("interns.gh.issue_view", return_value=_labels_response([labels.STATUS_REFINED])), \
             patch("interns.gh.issue_edit") as mock_edit:
            labels.apply_transition("o/r", 7, labels.estimation_needs_attention())
        mock_edit.assert_called_once_with(
            "o/r", 7, add_labels=[labels.STATUS_NEEDS_ATTENTION], remove_labels=[labels.STATUS_REFINED]
        )

    def test_a_failed_edit_raises(self):
        with patch("interns.gh.issue_view", return_value=_labels_response([])), \
             patch("interns.gh.issue_edit", side_effect=gh.GhCommandError("boom")):
            with self.assertRaises(gh.GhCommandError):
                labels.apply_transition("o/r", 7, labels.refinement_needs_attention())


class SetPrPipelineLabelTests(unittest.TestCase):
    def test_no_target_clears_the_present_label(self):
        with patch("interns.gh.pr_view", return_value=_labels_response(["pr:in-review", "size:S"])), \
             patch("interns.gh.pr_edit") as mock_edit:
            labels.set_pr_pipeline_label("o/r", 3)
        mock_edit.assert_called_once_with("o/r", 3, add_labels=[], remove_labels=["pr:in-review"])

    def test_swaps_to_the_target_label(self):
        with patch("interns.gh.pr_view", return_value=_labels_response(["pr:in-review"])), \
             patch("interns.gh.pr_edit") as mock_edit:
            labels.set_pr_pipeline_label("o/r", 3, "pr:coding")
        mock_edit.assert_called_once_with("o/r", 3, add_labels=["pr:coding"], remove_labels=["pr:in-review"])

    def test_noop_when_nothing_changes(self):
        with patch("interns.gh.pr_view", return_value=_labels_response(["size:S"])), \
             patch("interns.gh.pr_edit") as mock_edit:
            labels.set_pr_pipeline_label("o/r", 3)
        mock_edit.assert_not_called()

    def test_pickup_clears_a_stale_needs_attention(self):
        with patch("interns.gh.pr_view", return_value=_labels_response(["pr:needs-attention"])), \
             patch("interns.gh.pr_edit") as mock_edit:
            labels.set_pr_pipeline_label("o/r", 3, "pr:coding")
        mock_edit.assert_called_once_with("o/r", 3, add_labels=["pr:coding"], remove_labels=["pr:needs-attention"])

    def test_removing_an_absent_label_is_never_attempted(self):
        # The label-not-present case `|| true` used to mask: with nothing to
        # remove, gh_edit isn't even called, so there's no failure to swallow.
        with patch("interns.gh.pr_view", return_value=_labels_response([])), \
             patch("interns.gh.pr_edit") as mock_edit:
            labels.set_pr_pipeline_label("o/r", 3)
        mock_edit.assert_not_called()

    def test_a_failed_edit_does_not_raise(self):
        with patch("interns.gh.pr_view", return_value=_labels_response(["pr:in-review"])), \
             patch("interns.gh.pr_edit", side_effect=gh.GhCommandError("boom")):
            labels.set_pr_pipeline_label("o/r", 3, "pr:coding")  # does not raise


class EscalatePrTests(unittest.TestCase):
    def test_swaps_an_agent_label_for_needs_attention(self):
        with patch("interns.gh.pr_view", return_value=_labels_response(["pr:in-review"])), \
             patch("interns.gh.pr_edit") as mock_edit:
            labels.escalate_pr("o/r", 3)
        mock_edit.assert_called_once_with("o/r", 3, add_labels=["pr:needs-attention"], remove_labels=["pr:in-review"])


class EditIssueLabelsValidatedTests(unittest.TestCase):
    def test_noop_returns_nothing_to_do(self):
        self.assertEqual(labels.edit_issue_labels_validated("o/r", 7), "Nothing to do")

    def test_unknown_add_label_raises(self):
        with patch("interns.gh.label_list", return_value=[]):
            with self.assertRaisesRegex(gh.InvalidInputError, "don't exist"):
                labels.edit_issue_labels_validated("o/r", 7, add=["no-such"])

    def test_unknown_remove_label_raises(self):
        with patch("interns.gh.label_list", return_value=[]):
            with self.assertRaisesRegex(gh.InvalidInputError, "don't exist"):
                labels.edit_issue_labels_validated("o/r", 7, remove=["no-such"])


class ApplyRefinementTests(unittest.TestCase):
    def test_refined_without_type_label_raises(self):
        with self.assertRaisesRegex(gh.InvalidInputError, "type_label is required"):
            labels.apply_refinement("o/r", 5, "refined")

    def test_invalid_outcome_raises(self):
        with self.assertRaisesRegex(gh.InvalidInputError, "outcome must be"):
            labels.apply_refinement("o/r", 5, "done")


class ApplyEstimationTests(unittest.TestCase):
    def test_estimated_missing_scores_raises(self):
        with self.assertRaisesRegex(gh.InvalidInputError, "all required"):
            labels.apply_estimation("o/r", 7, "estimated")

    def test_estimated_bad_score_raises_value_error(self):
        with self.assertRaises(ValueError):
            labels.apply_estimation("o/r", 7, "estimated", "Low", "Medium", "Low", "Low")

    def test_invalid_outcome_raises(self):
        with self.assertRaisesRegex(gh.InvalidInputError, "outcome must be"):
            labels.apply_estimation("o/r", 7, "done")


if __name__ == "__main__":
    unittest.main()
