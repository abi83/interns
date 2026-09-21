import json
import unittest
from unittest import mock

from interns_install import gh_admin, safety
from interns_install.console import Console
from pipeline import gh
from interns_install.safety import (
    _protection_violation,
    check_branch_protection,
    check_metrics_branch,
    check_pages,
)


def _repo():
    return gh_admin.Repo(owner="acme", name="widgets", is_org=False)


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
        with mock.patch.object(gh_admin, "ref_exists", return_value=False), \
             mock.patch.object(gh_admin, "create_blob", return_value="blob-sha") as create_blob, \
             mock.patch.object(gh_admin, "create_tree", return_value="tree-sha") as create_tree, \
             mock.patch.object(gh_admin, "create_commit", return_value="commit-sha") as create_commit, \
             mock.patch.object(gh_admin, "create_branch") as create_branch, \
             mock.patch.object(gh_admin.gh, "api_status", return_value=("missing", None)), \
             mock.patch.object(gh_admin.gh, "api") as api:
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
            method="PUT", input_json=json.dumps(safety.METRICS_PROTECTION))

    def test_skips_creation_when_branch_already_exists(self):
        con = Console(assume_yes=True)
        with mock.patch.object(gh_admin, "ref_exists", return_value=True), \
             mock.patch.object(gh_admin, "create_branch") as create_branch, \
             mock.patch.object(gh_admin.gh, "api_status", return_value=("ok", {})):
            check_metrics_branch(con, _repo())
        create_branch.assert_not_called()

    def test_skips_protection_when_already_protected(self):
        con = Console(assume_yes=True)
        with mock.patch.object(gh_admin, "ref_exists", return_value=True), \
             mock.patch.object(gh_admin.gh, "api_status", return_value=("ok", {"allow_deletions": {"enabled": False}})), \
             mock.patch.object(gh_admin.gh, "api") as api:
            check_metrics_branch(con, _repo())
        api.assert_not_called()

    def test_blocked_protection_read_raises(self):
        con = Console(assume_yes=True)
        with mock.patch.object(gh_admin, "ref_exists", return_value=True), \
             mock.patch.object(gh_admin.gh, "api_status", return_value=("blocked", None)):
            with self.assertRaises(safety.SafetyCheckError):
                check_metrics_branch(con, _repo())

    def test_dry_run_makes_no_mutating_calls(self):
        con = Console(assume_yes=True, dry_run=True)
        with mock.patch.object(gh_admin, "ref_exists", return_value=False), \
             mock.patch.object(gh_admin, "create_blob") as create_blob, \
             mock.patch.object(gh_admin, "create_branch") as create_branch, \
             mock.patch.object(gh_admin.gh, "api_status", return_value=("missing", None)), \
             mock.patch.object(gh_admin.gh, "api") as api:
            check_metrics_branch(con, _repo())
        create_blob.assert_not_called()
        create_branch.assert_not_called()
        api.assert_not_called()


class CheckBranchProtectionTests(unittest.TestCase):
    def _run(self, state, body=None, *, put_error=None, **kwargs):
        con = kwargs.pop("con", Console(assume_yes=True))
        with mock.patch.object(gh_admin, "branch_protection_state", return_value=(state, body)), \
             mock.patch.object(gh_admin, "set_branch_protection", side_effect=put_error) as put:
            check_branch_protection(con, _repo(), "main", **kwargs)
        return con, put

    def test_blocked_raises(self):
        with self.assertRaises(safety.SafetyCheckError):
            self._run("blocked")

    def test_ok_without_violation_does_not_mutate(self):
        body = {"required_pull_request_reviews": {"required_approving_review_count": 1}}
        _, put = self._run("ok", body)
        put.assert_not_called()

    def test_ok_with_violation_raises(self):
        with self.assertRaisesRegex(safety.SafetyCheckError, "protected but"):
            self._run("ok", {"required_pull_request_reviews": None})

    def test_missing_applies_baseline(self):
        _, put = self._run("missing")
        put.assert_called_once_with("acme/widgets", "main", safety.BASELINE_PROTECTION)

    def test_missing_handled_externally_skips(self):
        _, put = self._run("missing", handled_externally=True)
        put.assert_not_called()

    def test_missing_dry_run_does_not_put(self):
        con, put = self._run("missing", con=Console(assume_yes=True, dry_run=True))
        put.assert_not_called()
        self.assertEqual(len(con.planned), 1)

    def test_put_failure_is_wrapped(self):
        with self.assertRaisesRegex(safety.SafetyCheckError, "baseline could not be applied: boom"):
            self._run("missing", put_error=gh.GhError("boom"))


class CheckPagesTests(unittest.TestCase):
    def _run(self, state, *, dry_run=False, enable_error=None):
        con = Console(assume_yes=True, dry_run=dry_run)
        with mock.patch.object(gh_admin, "pages_state", return_value=(state, None)), \
             mock.patch.object(gh_admin, "enable_pages", side_effect=enable_error) as enable:
            check_pages(con, _repo())
        return enable

    def test_blocked_raises(self):
        with self.assertRaises(safety.SafetyCheckError):
            self._run("blocked")

    def test_already_enabled(self):
        self._run("ok").assert_not_called()

    def test_missing_enables(self):
        self._run("missing").assert_called_once_with("acme/widgets")

    def test_dry_run_does_not_enable(self):
        self._run("missing", dry_run=True).assert_not_called()

    def test_enable_failure_is_wrapped(self):
        with self.assertRaisesRegex(safety.SafetyCheckError, "could not be enabled: boom"):
            self._run("missing", enable_error=gh.GhError("boom"))


class CreateMetricsBranchFailureTests(unittest.TestCase):
    def test_creation_failure_is_wrapped(self):
        con = Console(assume_yes=True)
        with mock.patch.object(gh_admin, "ref_exists", return_value=False), \
             mock.patch.object(gh_admin, "create_blob", side_effect=gh.GhError("boom")):
            with self.assertRaisesRegex(safety.SafetyCheckError, "could not create"):
                check_metrics_branch(con, _repo())

    def test_protection_put_failure_is_wrapped(self):
        con = Console(assume_yes=True)
        with mock.patch.object(gh_admin, "ref_exists", return_value=True), \
             mock.patch.object(gh_admin, "branch_protection_state", return_value=("missing", None)), \
             mock.patch.object(gh_admin, "set_branch_protection", side_effect=gh.GhError("boom")):
            with self.assertRaisesRegex(safety.SafetyCheckError, "could not be protected: boom"):
                check_metrics_branch(con, _repo())


if __name__ == "__main__":
    unittest.main()
