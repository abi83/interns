import unittest

from interns_install.safety import _protection_violation


class ProtectionViolationTests(unittest.TestCase):
    def test_ok_when_review_required_and_no_bots_granted(self):
        body = {"required_pull_request_reviews": {"required_approving_review_count": 1},
                "restrictions": None}
        self.assertIsNone(_protection_violation(body, ["github-actions[bot]"]))

    def test_flags_missing_review_requirement(self):
        body = {"required_pull_request_reviews": None, "restrictions": None}
        violation = _protection_violation(body, ["github-actions[bot]"])
        self.assertIn("does not require a pull request review", violation)

    def test_flags_bot_on_user_allowlist(self):
        body = {
            "required_pull_request_reviews": {"required_approving_review_count": 1},
            "restrictions": {"users": [{"login": "github-actions[bot]"}], "teams": [], "apps": []},
        }
        violation = _protection_violation(body, ["github-actions[bot]"])
        self.assertIn("github-actions[bot]", violation)

    def test_flags_app_on_allowlist(self):
        body = {
            "required_pull_request_reviews": {"required_approving_review_count": 1},
            "restrictions": {"users": [], "teams": [], "apps": [{"slug": "interns-coder"}]},
        }
        violation = _protection_violation(body, ["interns-coder[bot]"])
        self.assertIn("interns-coder[bot]", violation)


if __name__ == "__main__":
    unittest.main()
