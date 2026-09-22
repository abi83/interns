import io
import os
import unittest
from unittest.mock import patch

from pipeline import gh, run_summary
from pipeline.ctx import ActionsCtx
from pipeline.verdict import Review

REPO = "owner/repo"
SERVER = "https://github.com"
RUN_URL = f"{SERVER}/{REPO}/actions/runs/42"


def _patch(**overrides):
    """Patch run_summary's collaborators with sane no-op defaults, overridden
    per test. Mirrors the bats stub's STUB_* knobs."""
    defaults = dict(
        issue_view=lambda repo, issue, fields: {"title": ""},
        pr_view=lambda repo, pr, fields: {"title": "", "headRefOid": ""},
        pr_diff_names=lambda repo, pr: [],
        issue_labels=lambda repo, issue: [],
        all_reviews=lambda repo, pr: [],
        reviews_by=lambda repo, pr, login: [],
    )
    defaults.update(overrides)
    return (
        patch("pipeline.run_summary.gh.issue_view", side_effect=defaults["issue_view"]),
        patch("pipeline.run_summary.gh.pr_view", side_effect=defaults["pr_view"]),
        patch("pipeline.run_summary.gh.pr_diff_names", side_effect=defaults["pr_diff_names"]),
        patch("pipeline.run_summary.labels.issue_labels", side_effect=defaults["issue_labels"]),
        patch("pipeline.run_summary.verdict.all_reviews", side_effect=defaults["all_reviews"]),
        patch("pipeline.run_summary.verdict.reviews_by", side_effect=defaults["reviews_by"]),
    )


class CoderSectionTests(unittest.TestCase):
    def test_issue_round_pr_outcome_files_cost_final_message(self):
        patches = _patch(
            issue_view=lambda repo, issue, fields: {"title": "Add a widget"},
            pr_diff_names=lambda repo, pr: ["src/a.ts", "src/b.ts", "src/c.ts"],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(
                REPO, SERVER, "Coder", None, issue="42", pr="99", round_="initial",
            )
        self.assertIn("## Coder run", summary)
        self.assertIn("**Issue:** [#42](https://github.com/owner/repo/issues/42) — Add a widget", summary)
        self.assertIn("**Round:** Initial implementation", summary)
        self.assertIn("**Outcome:** PR opened — [#99](https://github.com/owner/repo/pull/99)", summary)
        self.assertIn("**Files changed:** 3", summary)
        self.assertNotIn("checks", summary.lower())

    def test_a_failed_diff_lookup_reads_unknown_not_zero(self):
        def boom(*a, **k):
            raise gh.GhCommandError("rate limited")
        patches = _patch(pr_diff_names=boom)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch("sys.stderr", io.StringIO()):
            summary = run_summary.build_summary(
                REPO, SERVER, "Coder", None, issue="42", pr="99", round_="initial",
            )
        self.assertIn("**Files changed:** unknown", summary)

    def test_no_pr_opened_surfaces_a_blocked_outcome_without_the_log(self):
        patches = _patch()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(
                REPO, SERVER, "Coder", None, issue="42", pr="", round_="initial",
            )
        self.assertIn("**Outcome:** ⚠️ No PR — see the final message below.", summary)
        self.assertNotIn("Files changed", summary)

    def test_fix_round_that_pushed_a_new_commit_shows_pr_updated(self):
        patches = _patch(
            all_reviews=lambda repo, pr: [
                Review("someone", "CHANGES_REQUESTED", "oldsha"),
                Review("someone-else", "CHANGES_REQUESTED", "oldsha"),
            ],
            pr_view=lambda repo, pr, fields: {"headRefOid": "newsha"},
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(
                REPO, SERVER, "Coder", None, issue="42", pr="99", round_="fix",
            )
        self.assertIn("**Round:** Fix round 2", summary)
        self.assertIn("**Outcome:** PR updated — [#99](https://github.com/owner/repo/pull/99)", summary)

    def test_fix_round_that_pushed_nothing_shows_the_blocked_outcome(self):
        patches = _patch(
            all_reviews=lambda repo, pr: [Review("someone", "CHANGES_REQUESTED", "samesha")],
            pr_view=lambda repo, pr, fields: {"headRefOid": "samesha"},
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(
                REPO, SERVER, "Coder", None, issue="42", pr="99", round_="fix",
            )
        self.assertIn("**Outcome:** ⚠️ No new commit pushed — see the final message below.", summary)

    def test_fix_round_with_no_changes_requested_reviews_shows_fix_round_zero(self):
        patches = _patch()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(
                REPO, SERVER, "Coder", None, issue="42", pr="99", round_="fix",
            )
        self.assertIn("**Round:** Fix round 0", summary)

    def test_a_failed_review_lookup_on_a_fix_round_omits_the_count(self):
        def boom(*a, **k):
            raise gh.GhCommandError("rate limited")
        patches = _patch(all_reviews=boom)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch("sys.stderr", io.StringIO()):
            summary = run_summary.build_summary(
                REPO, SERVER, "Coder", None, issue="42", pr="99", round_="fix",
            )
        self.assertIn("**Round:** Fix round\n", summary)


class ReviewSectionTests(unittest.TestCase):
    def test_a_failed_review_lookup_shows_outcome_unavailable_and_warns(self):
        def boom(*a, **k):
            raise gh.GhCommandError("rate limited")
        patches = _patch(reviews_by=boom)
        buf = io.StringIO()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch("sys.stderr", buf):
            summary = run_summary.build_summary(
                REPO, SERVER, "Review", None, pr="99", reviewer_bot="reviewer-app[bot]",
            )
        self.assertIn("Review lookup failed", summary)
        self.assertIn("warning:", buf.getvalue())

    def test_approved_verdict(self):
        patches = _patch(
            pr_view=lambda repo, pr, fields: {"title": "feat: widget", "headRefOid": "headsha"},
            reviews_by=lambda repo, pr, login: [Review(login, "APPROVED", "headsha")],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(
                REPO, SERVER, "Review", None, pr="99", issue="42", reviewer_bot="reviewer-app[bot]",
            )
        self.assertIn("**PR:** [#99](https://github.com/owner/repo/pull/99) — feat: widget", summary)
        self.assertIn("**Round:** initial review", summary)
        self.assertIn("**Outcome:** ✅ Approved", summary)

    def test_no_verdict_submitted(self):
        patches = _patch(
            pr_view=lambda repo, pr, fields: {"title": "", "headRefOid": "headsha"},
            reviews_by=lambda repo, pr, login: [Review(login, "CHANGES_REQUESTED", "oldsha")],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(
                REPO, SERVER, "Review", None, pr="99", reviewer_bot="reviewer-app[bot]",
            )
        self.assertIn("**Round:** re-review (after 1 changes-requested)", summary)
        self.assertIn("**Outcome:** ⚠️ No verdict submitted — see the final message below.", summary)

    def test_first_ever_review_requesting_changes_is_initial_not_re_review(self):
        patches = _patch(
            pr_view=lambda repo, pr, fields: {"title": "", "headRefOid": "head1"},
            reviews_by=lambda repo, pr, login: [Review(login, "CHANGES_REQUESTED", "head1")],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(
                REPO, SERVER, "Review", None, pr="99", reviewer_bot="reviewer-app[bot]",
            )
        self.assertIn("**Round:** initial review", summary)
        self.assertIn("**Outcome:** 🔴 Changes requested", summary)

    def test_a_genuine_re_review_counts_only_prior_commit_changes_requested(self):
        patches = _patch(
            pr_view=lambda repo, pr, fields: {"title": "", "headRefOid": "head2"},
            reviews_by=lambda repo, pr, login: [
                Review(login, "CHANGES_REQUESTED", "head1"),
                Review(login, "CHANGES_REQUESTED", "head2"),
            ],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(
                REPO, SERVER, "Review", None, pr="99", reviewer_bot="reviewer-app[bot]",
            )
        self.assertIn("**Round:** re-review (after 1 changes-requested)", summary)
        self.assertIn("**Outcome:** 🔴 Changes requested", summary)

    def test_a_stale_verdict_against_an_old_commit_is_not_counted_as_this_runs(self):
        patches = _patch(
            pr_view=lambda repo, pr, fields: {"title": "", "headRefOid": "newsha"},
            reviews_by=lambda repo, pr, login: [Review(login, "CHANGES_REQUESTED", "oldsha")],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(
                REPO, SERVER, "Review", None, pr="99", reviewer_bot="reviewer-app[bot]",
            )
        self.assertIn("**Outcome:** ⚠️ No verdict submitted — see the final message below.", summary)


class RefinementSectionTests(unittest.TestCase):
    def test_a_failed_label_lookup_shows_outcome_unavailable_and_warns(self):
        def boom(*a, **k):
            raise gh.GhCommandError("rate limited")
        patches = _patch(issue_labels=boom)
        buf = io.StringIO()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch("sys.stderr", buf):
            summary = run_summary.build_summary(REPO, SERVER, "Refinement", None, issue="7")
        self.assertIn("Label lookup failed", summary)
        self.assertIn("warning:", buf.getvalue())

    def test_body_refined(self):
        patches = _patch(
            issue_view=lambda repo, issue, fields: {"title": "Vague idea"},
            issue_labels=lambda repo, issue: ["type:coding-task", "status:refined"],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(REPO, SERVER, "Refinement", None, issue="7")
        self.assertIn("## Refinement run", summary)
        self.assertIn("**Outcome:** Body refined", summary)

    def test_stopped_for_clarification(self):
        patches = _patch(issue_labels=lambda repo, issue: ["status:needs-attention"])
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(REPO, SERVER, "Refinement", None, issue="7")
        self.assertIn("**Outcome:** ⚠️ Stopped for clarification — see the final message below.", summary)


class EstimationSectionTests(unittest.TestCase):
    def test_a_failed_label_lookup_shows_outcome_unavailable(self):
        def boom(*a, **k):
            raise gh.GhCommandError("rate limited")
        patches = _patch(issue_labels=boom)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch("sys.stderr", io.StringIO()):
            summary = run_summary.build_summary(REPO, SERVER, "Estimation", None, issue="7")
        self.assertIn("Label lookup failed", summary)

    def test_estimate_posted_with_size_label(self):
        patches = _patch(issue_labels=lambda repo, issue: ["type:coding-task", "status:estimated", "size:M"])
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(REPO, SERVER, "Estimation", None, issue="7")
        self.assertIn("**Outcome:** Estimate posted — `size:M`", summary)


class CostAndExecFileTests(unittest.TestCase):
    def test_missing_execution_file_yields_an_unknown_cost_and_a_placeholder_message(self):
        patches = _patch(issue_labels=lambda repo, issue: [])
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(REPO, SERVER, "Refinement", "/no/such/file", issue="7")
        self.assertIn("**Cost:** $unknown", summary)
        self.assertIn("> _No final message — the run produced no result output._", summary)

    def test_missing_execution_file_reports_a_timeout(self):
        patches = _patch()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(REPO, SERVER, "Refinement", None, issue="7", cost_warn="0.30")
        self.assertIn("killed (timed out) before writing results", summary)

    def test_cost_over_the_warn_limit_adds_a_warning_line(self, ):
        patches = _patch(issue_labels=lambda repo, issue: ["status:refined"])
        exec_file = self._write_exec({"total_cost_usd": 2.5, "result": "done"})
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(REPO, SERVER, "Refinement", exec_file, issue="7", cost_warn="0.30")
        self.assertIn("⚠️ cost $2.5000 over the $0.30 warn limit", summary)

    def test_cost_under_the_warn_limit_adds_no_warning_line(self):
        patches = _patch(issue_labels=lambda repo, issue: ["status:refined"])
        exec_file = self._write_exec({"total_cost_usd": 0.10, "result": "done"})
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = run_summary.build_summary(REPO, SERVER, "Refinement", exec_file, issue="7", cost_warn="0.30")
        self.assertNotIn("warn limit", summary)

    def _write_exec(self, result_fields: dict) -> str:
        import json
        import tempfile
        entry = {"type": "result", **result_fields}
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, "w") as f:
            json.dump([entry], f)
        self.addCleanup(os.remove, path)
        return path


class UnknownPhaseTests(unittest.TestCase):
    def test_errors_on_an_unknown_phase(self):
        patches = _patch()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            with self.assertRaises(ValueError):
                run_summary.build_summary(REPO, SERVER, "Bogus", None, issue="7")


class RoundLineTests(unittest.TestCase):
    def test_fix_with_a_count(self):
        self.assertEqual(run_summary._round_line("fix", "2"), "Fix round 2")

    def test_fix_with_no_count(self):
        self.assertEqual(run_summary._round_line("fix", ""), "Fix round")

    def test_initial(self):
        self.assertEqual(run_summary._round_line("initial", ""), "Initial implementation")

    def test_unknown_round_is_blank(self):
        self.assertEqual(run_summary._round_line("", ""), "")


class CliTests(unittest.TestCase):
    def test_writes_the_summary_to_github_step_summary(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = os.path.join(tmp, "summary.md")
            open(summary_path, "w").close()
            ctx = ActionsCtx(repo=REPO, token="", server_url=SERVER, run_id="42",
                             run_attempt=1, workspace=".", event_name="",
                             reviewer_bot="", step_summary=summary_path)
            patches = _patch(issue_labels=lambda repo, issue: ["status:needs-attention"])
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                run_summary._main(ctx, ["--phase", "Refinement", "--issue", "7"])
            content = open(summary_path).read()
        self.assertIn("## Refinement run", content)
        self.assertIn("Stopped for clarification", content)


if __name__ == "__main__":
    unittest.main()
