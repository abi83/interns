import unittest
from unittest import mock

from interns_install import gh, safety
from interns_install.console import Console
from interns_install.safety import _protection_violation, check_metrics_branch


def _repo():
    return gh.Repo(owner="acme", name="widgets", is_org=False)


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


class CheckMetricsBranchTests(unittest.TestCase):
    def test_creates_orphan_branch_and_protection_when_both_missing(self):
        con = Console(assume_yes=True)
        with mock.patch.object(gh, "ref_exists", return_value=False), \
             mock.patch.object(gh, "create_blob", return_value="blob-sha") as create_blob, \
             mock.patch.object(gh, "create_tree", return_value="tree-sha") as create_tree, \
             mock.patch.object(gh, "create_commit", return_value="commit-sha") as create_commit, \
             mock.patch.object(gh, "create_branch") as create_branch, \
             mock.patch.object(gh, "api_status", return_value=("missing", None)), \
             mock.patch.object(gh, "api") as api:
            check_metrics_branch(con, _repo())

        create_blob.assert_called_once_with("acme/widgets", "")
        create_tree.assert_called_once_with("acme/widgets", [
            {"path": "metrics.jsonl", "mode": "100644", "type": "blob", "sha": "blob-sha"},
        ])
        create_commit.assert_called_once_with(
            "acme/widgets", mock.ANY, "tree-sha", parents=[])
        create_branch.assert_called_once_with("acme/widgets", "metrics", "commit-sha")
        api.assert_called_once_with(
            "repos/acme/widgets/branches/metrics/protection",
            method="PUT", input_json=safety.METRICS_PROTECTION)

    def test_skips_creation_when_branch_already_exists(self):
        con = Console(assume_yes=True)
        with mock.patch.object(gh, "ref_exists", return_value=True), \
             mock.patch.object(gh, "create_branch") as create_branch, \
             mock.patch.object(gh, "api_status", return_value=("ok", {})):
            check_metrics_branch(con, _repo())
        create_branch.assert_not_called()

    def test_skips_protection_when_already_protected(self):
        con = Console(assume_yes=True)
        with mock.patch.object(gh, "ref_exists", return_value=True), \
             mock.patch.object(gh, "api_status", return_value=("ok", {"allow_deletions": {"enabled": False}})), \
             mock.patch.object(gh, "api") as api:
            check_metrics_branch(con, _repo())
        api.assert_not_called()

    def test_blocked_protection_read_raises(self):
        con = Console(assume_yes=True)
        with mock.patch.object(gh, "ref_exists", return_value=True), \
             mock.patch.object(gh, "api_status", return_value=("blocked", None)):
            with self.assertRaises(safety.SafetyCheckError):
                check_metrics_branch(con, _repo())

    def test_dry_run_makes_no_mutating_calls(self):
        con = Console(assume_yes=True, dry_run=True)
        with mock.patch.object(gh, "ref_exists", return_value=False), \
             mock.patch.object(gh, "create_blob") as create_blob, \
             mock.patch.object(gh, "create_branch") as create_branch, \
             mock.patch.object(gh, "api_status", return_value=("missing", None)), \
             mock.patch.object(gh, "api") as api:
            check_metrics_branch(con, _repo())
        create_blob.assert_not_called()
        create_branch.assert_not_called()
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
