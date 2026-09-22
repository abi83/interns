import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import wait_for_checks
from testkit.harness import default_ctx


def chk(name, bucket, run="99"):
    return {"name": name, "bucket": bucket, "link": f"https://github.com/owner/repo/actions/runs/{run}/job/1"}


class WaitForChecksTests(unittest.TestCase):
    def test_every_check_green_is_ok(self):
        checks = [chk("test", "pass"), chk("build", "pass"), chk("lint", "pass"), chk("coverage", "skipping")]
        with patch("pipeline.wait_for_checks.gh.pr_checks", return_value=checks):
            ok, reason = wait_for_checks.wait_for_checks("acme/widgets", 5, "42", [], settle=0, sleep=lambda s: None)
        self.assertTrue(ok)
        self.assertEqual(reason, "")

    def test_one_red_check_fails_with_a_reason_naming_it(self):
        checks = [chk("test", "pass"), chk("lint", "fail"), chk("typecheck", "pass")]
        with patch("pipeline.wait_for_checks.gh.pr_checks", return_value=checks):
            ok, reason = wait_for_checks.wait_for_checks("acme/widgets", 5, "42", [], settle=0, sleep=lambda s: None)
        self.assertFalse(ok)
        self.assertEqual(reason, "red checks: lint=fail")

    def test_a_cancelled_check_counts_as_red(self):
        checks = [chk("test", "pass"), chk("build", "cancel")]
        with patch("pipeline.wait_for_checks.gh.pr_checks", return_value=checks):
            ok, reason = wait_for_checks.wait_for_checks("acme/widgets", 5, "42", [], settle=0, sleep=lambda s: None)
        self.assertFalse(ok)
        self.assertIn("build=cancel", reason)

    def test_a_pending_check_that_later_passes_resolves_ok(self):
        seq = iter([[chk("test", "pending")], [chk("test", "pass")]])
        with patch("pipeline.wait_for_checks.gh.pr_checks", side_effect=lambda repo, pr: next(seq)):
            ok, _ = wait_for_checks.wait_for_checks("acme/widgets", 5, "42", [], settle=0, sleep=lambda s: None)
        self.assertTrue(ok)

    def test_the_runs_own_checks_are_excluded(self):
        checks = [chk("pipeline / reviewer", "pending", run="42")]
        with patch("pipeline.wait_for_checks.gh.pr_checks", return_value=checks):
            ok, _ = wait_for_checks.wait_for_checks("acme/widgets", 5, "42", [], settle=0, sleep=lambda s: None)
        self.assertTrue(ok)

    def test_ignored_checks_are_dropped(self):
        checks = [chk("test", "pass"), chk("preview-deploy", "fail")]
        with patch("pipeline.wait_for_checks.gh.pr_checks", return_value=checks):
            ok, _ = wait_for_checks.wait_for_checks("acme/widgets", 5, "42", ["preview-deploy"], settle=0, sleep=lambda s: None)
        self.assertTrue(ok)

    def test_no_checks_at_all_is_ok_after_the_settle_window(self):
        with patch("pipeline.wait_for_checks.gh.pr_checks", return_value=[]):
            times = iter([0, 5])
            ok, _ = wait_for_checks.wait_for_checks(
                "acme/widgets", 5, "42", [], settle=1, sleep=lambda s: None, monotonic=lambda: next(times),
            )
        self.assertTrue(ok)

    def test_times_out_when_a_check_never_resolves(self):
        checks = [chk("test", "pending"), chk("build", "pass")]
        with patch("pipeline.wait_for_checks.gh.pr_checks", return_value=checks):
            ok, reason = wait_for_checks.wait_for_checks(
                "acme/widgets", 5, "42", [], timeout=0, settle=0, sleep=lambda s: None,
            )
        self.assertFalse(ok)
        self.assertIn("timed out waiting for checks to finish: test", reason)


class CliTests(unittest.TestCase):
    def _ctx(self, event_name=""):
        return default_ctx(run_id="42", event_name=event_name)

    def test_workflow_dispatch_skips_the_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}), \
                 patch("pipeline.wait_for_checks.wait_for_checks") as fn:
                wait_for_checks._main(self._ctx(event_name="workflow_dispatch"), ["--pr", "5"])
            fn.assert_not_called()
            self.assertEqual(Path(output_file).read_text(), "ok=true\n")

    def test_writes_ok_false_and_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}), \
                 patch("pipeline.wait_for_checks.config.checks_ignore", return_value=[]), \
                 patch("pipeline.wait_for_checks.config.load_raw", return_value={}), \
                 patch("pipeline.wait_for_checks.wait_for_checks", return_value=(False, "red checks: lint=fail")):
                wait_for_checks._main(self._ctx(), ["--pr", "5"])
            self.assertEqual(Path(output_file).read_text(), "ok=false\nreason=red checks: lint=fail\n")


if __name__ == "__main__":
    unittest.main()
