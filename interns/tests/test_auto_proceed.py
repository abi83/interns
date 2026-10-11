import unittest
from unittest.mock import patch

from interns.steps import auto_proceed

SIZES = {"XS": True, "S": True, "M": True, "L": False, "XL": False}


def _proceed(current: list[str], sizes: dict[str, bool] = SIZES):
    with patch("interns.steps.auto_proceed.labels.issue_labels", return_value=current), \
         patch("interns.steps.auto_proceed.labels.apply_transition") as transition, \
         patch("interns.steps.auto_proceed.gh.issue_comment") as comment:
        size = auto_proceed.proceed("acme/widgets", 7, sizes)
    return size, transition, comment


class ProceedTests(unittest.TestCase):
    def test_enabled_size_moves_to_ready_and_comments(self):
        size, transition, comment = _proceed(["status:estimated", "type:coding-task", "size:M"])
        self.assertEqual(size, "M")
        applied = transition.call_args.args[2]
        self.assertEqual((applied.add, applied.remove), (["status:ready"], ["status:estimated"]))
        comment.assert_called_once()

    def test_disabled_size_is_left_for_a_human(self):
        size, transition, comment = _proceed(["status:estimated", "type:bug", "size:L"])
        self.assertIsNone(size)
        transition.assert_not_called()
        comment.assert_not_called()

    def test_spike_never_proceeds(self):
        size, transition, _ = _proceed(["status:estimated", "type:spike", "size:XS"])
        self.assertIsNone(size)
        transition.assert_not_called()

    def test_issue_not_on_estimated_is_ignored(self):
        size, transition, _ = _proceed(["status:needs-attention", "type:bug", "size:XS"])
        self.assertIsNone(size)
        transition.assert_not_called()

    def test_missing_size_label_is_ignored(self):
        size, transition, _ = _proceed(["status:estimated", "type:bug"])
        self.assertIsNone(size)
        transition.assert_not_called()
