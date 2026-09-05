import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from interns_install.safety import _config_allows_agent_push, _protection_violation


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


class ConfigAllowsAgentPushTests(unittest.TestCase):
    def test_false_when_file_absent(self):
        self.assertFalse(_config_allows_agent_push(Path("/nonexistent/agent-pipeline.yml")))

    def test_true_when_set(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent-pipeline.yml"
            path.write_text("allow_agent_push_to_default_branch: true\n")
            self.assertTrue(_config_allows_agent_push(path))

    def test_false_when_unset_or_other_keys_present(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent-pipeline.yml"
            path.write_text("some_other_key: true\n")
            self.assertFalse(_config_allows_agent_push(path))

    def test_false_when_explicitly_false(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent-pipeline.yml"
            path.write_text("allow_agent_push_to_default_branch: false\n")
            self.assertFalse(_config_allows_agent_push(path))


if __name__ == "__main__":
    unittest.main()
