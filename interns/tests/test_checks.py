import unittest
from unittest.mock import patch

from interns.domain import checks


def chk(name, bucket, run="99"):
    return {"name": name, "bucket": bucket, "link": f"https://github.com/owner/repo/actions/runs/{run}/job/1"}


def _wait(repo, pr, run_id, ignore, **kwargs):
    return checks.wait_for_checks(
        repo, pr, run_id, ignore, **{"timeout": 1200, "poll": 20, "settle": 30, **kwargs},
    )


class WaitForChecksTests(unittest.TestCase):
    def test_every_check_green_is_ok(self):
        checks = [chk("test", "pass"), chk("build", "pass"), chk("lint", "pass"), chk("coverage", "skipping")]
        with patch("interns.domain.checks.gh.pr_checks", return_value=checks):
            ok, reason = _wait("acme/widgets", 5, "42", [], settle=0, sleep=lambda s: None)
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_one_red_check_fails_with_a_reason_naming_it(self):
        checks = [chk("test", "pass"), chk("lint", "fail"), chk("typecheck", "pass")]
        with patch("interns.domain.checks.gh.pr_checks", return_value=checks):
            ok, reason = _wait("acme/widgets", 5, "42", [], settle=0, sleep=lambda s: None)
        self.assertFalse(ok)
        self.assertEqual(reason, "red checks: lint=fail")

    def test_a_cancelled_check_counts_as_red(self):
        checks = [chk("test", "pass"), chk("build", "cancel")]
        with patch("interns.domain.checks.gh.pr_checks", return_value=checks):
            ok, reason = _wait("acme/widgets", 5, "42", [], settle=0, sleep=lambda s: None)
        self.assertFalse(ok)
        self.assertIn("build=cancel", reason)

    def test_a_pending_check_that_later_passes_resolves_ok(self):
        seq = iter([[chk("test", "pending")], [chk("test", "pass")]])
        with patch("interns.domain.checks.gh.pr_checks", side_effect=lambda repo, pr: next(seq)):
            ok, _ = _wait("acme/widgets", 5, "42", [], settle=0, sleep=lambda s: None)
        self.assertTrue(ok)

    def test_the_runs_own_checks_are_excluded(self):
        checks = [chk("pipeline / reviewer", "pending", run="42")]
        with patch("interns.domain.checks.gh.pr_checks", return_value=checks):
            ok, _ = _wait("acme/widgets", 5, "42", [], settle=0, sleep=lambda s: None)
        self.assertTrue(ok)

    def test_ignored_checks_are_dropped(self):
        checks = [chk("test", "pass"), chk("preview-deploy", "fail")]
        with patch("interns.domain.checks.gh.pr_checks", return_value=checks):
            ok, _ = _wait("acme/widgets", 5, "42", ["preview-deploy"], settle=0, sleep=lambda s: None)
        self.assertTrue(ok)

    def test_no_checks_at_all_is_ok_after_the_settle_window(self):
        with patch("interns.domain.checks.gh.pr_checks", return_value=[]):
            times = iter([0, 5])
            ok, _ = _wait(
                "acme/widgets", 5, "42", [], settle=1, sleep=lambda s: None, monotonic=lambda: next(times),
            )
        self.assertTrue(ok)

    def test_times_out_when_a_check_never_resolves(self):
        checks = [chk("test", "pending"), chk("build", "pass")]
        with patch("interns.domain.checks.gh.pr_checks", return_value=checks):
            ok, reason = _wait(
                "acme/widgets", 5, "42", [], timeout=0, settle=0, sleep=lambda s: None,
            )
        self.assertFalse(ok)
        self.assertIn("timed out waiting for checks to finish: test", reason)


class RouteRedChecksTests(unittest.TestCase):
    def test_escalates_the_pr_and_comments_the_reason_with_the_run_link(self):
        with patch("interns.domain.checks.labels.escalate_pr") as escalate, \
             patch("interns.domain.checks.gh.pr_comment") as comment:
            checks.route_red_checks("acme/widgets", 5, "red checks: lint=fail", run_url="https://github.example/run/1")
        escalate.assert_called_once_with("acme/widgets", 5)
        body = comment.call_args[0][2]
        self.assertIn("red checks: lint=fail", body)
        self.assertIn("Run: https://github.example/run/1", body)


if __name__ == "__main__":
    unittest.main()
