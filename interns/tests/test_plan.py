import unittest

from interns.domain import plan


class IsStaleTriggerTests(unittest.TestCase):
    def test_ready_issue_is_not_stale(self):
        self.assertFalse(plan.is_stale_trigger(["status:ready", "type:bug"]))

    def test_in_progress_issue_is_stale(self):
        self.assertTrue(plan.is_stale_trigger(["status:in-progress", "type:bug"]))

    def test_needs_attention_issue_is_stale(self):
        self.assertTrue(plan.is_stale_trigger(["status:needs-attention"]))

    def test_issue_without_labels_is_not_stale(self):
        self.assertFalse(plan.is_stale_trigger([]))


class IsForeignBotTests(unittest.TestCase):
    def test_the_coders_own_app_is_not_foreign(self):
        self.assertFalse(plan.is_foreign_bot("interns-coder[bot]", "Bot", "interns-coder[bot]"))

    def test_another_bot_is_foreign(self):
        self.assertTrue(plan.is_foreign_bot("dependabot[bot]", "Bot", "interns-coder[bot]"))

    def test_a_human_is_not_foreign(self):
        self.assertFalse(plan.is_foreign_bot("alice", "User", "interns-coder[bot]"))

    def test_a_dispatch_without_an_author_is_not_foreign(self):
        self.assertFalse(plan.is_foreign_bot("", "", "interns-coder[bot]"))


if __name__ == "__main__":
    unittest.main()
