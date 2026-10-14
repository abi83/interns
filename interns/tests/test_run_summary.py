import io
import os
import unittest
from unittest.mock import patch

from interns import cli, gh
from interns.steps import run_summary
from interns.steps.run_summary import CoderRun, EstimationRun, RefinementRun, ReviewRun, Round
from interns.ctx import ActionsCtx
from interns.domain.verdict import Review, ReviewState

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
        patch("interns.steps.run_summary.gh.issue_view", side_effect=defaults["issue_view"]),
        patch("interns.steps.run_summary.gh.pr_view", side_effect=defaults["pr_view"]),
        patch("interns.steps.run_summary.gh.pr_diff_names", side_effect=defaults["pr_diff_names"]),
        patch("interns.steps.run_summary.labels.issue_labels", side_effect=defaults["issue_labels"]),
        patch("interns.steps.run_summary.verdict.all_reviews", side_effect=defaults["all_reviews"]),
        patch("interns.steps.run_summary.verdict.reviews_by", side_effect=defaults["reviews_by"]),
    )


def _build(run, exec_file, cost_warn=None):
    return run_summary.build_summary(run_summary.RunInfo(REPO, SERVER, RUN_URL, cost_warn), run, exec_file)


class CoderSectionTests(unittest.TestCase):
    def test_issue_round_pr_outcome_files_cost_final_message(self):
        patches = _patch(
            issue_view=lambda repo, issue, fields: {"title": "Add a widget"},
            pr_diff_names=lambda repo, pr: ["src/a.ts", "src/b.ts", "src/c.ts"],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(CoderRun(42, 99, Round.INITIAL), None)
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
            summary = _build(CoderRun(42, 99, Round.INITIAL), None)
        self.assertIn("**Files changed:** unknown", summary)

    def test_no_pr_opened_surfaces_a_blocked_outcome_without_the_log(self):
        patches = _patch()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(CoderRun(42, None, Round.INITIAL), None)
        self.assertIn("**Outcome:** ⚠️ No PR — see the final message below.", summary)
        self.assertNotIn("Files changed", summary)

    def test_fix_round_that_pushed_a_new_commit_shows_pr_updated(self):
        patches = _patch(
            all_reviews=lambda repo, pr: [
                Review("someone", ReviewState.CHANGES_REQUESTED, "oldsha"),
                Review("someone-else", ReviewState.CHANGES_REQUESTED, "oldsha"),
            ],
            pr_view=lambda repo, pr, fields: {"headRefOid": "newsha"},
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(CoderRun(42, 99, Round.FIX), None)
        self.assertIn("**Round:** Fix round 2", summary)
        self.assertIn("**Outcome:** PR updated — [#99](https://github.com/owner/repo/pull/99)", summary)

    def test_fix_round_that_pushed_nothing_shows_the_blocked_outcome(self):
        patches = _patch(
            all_reviews=lambda repo, pr: [Review("someone", ReviewState.CHANGES_REQUESTED, "samesha")],
            pr_view=lambda repo, pr, fields: {"headRefOid": "samesha"},
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(CoderRun(42, 99, Round.FIX), None)
        self.assertIn("**Outcome:** ⚠️ No new commit pushed — see the final message below.", summary)

    def test_fix_round_with_no_changes_requested_reviews_shows_fix_round_zero(self):
        patches = _patch()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(CoderRun(42, 99, Round.FIX), None)
        self.assertIn("**Round:** Fix round 0", summary)

    def test_a_failed_review_lookup_on_a_fix_round_omits_the_count(self):
        def boom(*a, **k):
            raise gh.GhCommandError("rate limited")
        patches = _patch(all_reviews=boom)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch("sys.stderr", io.StringIO()):
            summary = _build(CoderRun(42, 99, Round.FIX), None)
        self.assertIn("**Round:** Fix round\n", summary)


class ReviewSectionTests(unittest.TestCase):
    def test_a_failed_review_lookup_shows_outcome_unavailable_and_warns(self):
        def boom(*a, **k):
            raise gh.GhCommandError("rate limited")
        patches = _patch(reviews_by=boom)
        buf = io.StringIO()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch("sys.stderr", buf):
            summary = _build(ReviewRun(99, "reviewer-app[bot]"), None)
        self.assertIn("Review lookup failed", summary)
        self.assertIn("warning:", buf.getvalue())

    def test_approved_verdict(self):
        patches = _patch(
            pr_view=lambda repo, pr, fields: {"title": "feat: widget", "headRefOid": "headsha"},
            reviews_by=lambda repo, pr, login: [Review(login, ReviewState.APPROVED, "headsha")],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(ReviewRun(99, "reviewer-app[bot]"), None)
        self.assertIn("**PR:** [#99](https://github.com/owner/repo/pull/99) — feat: widget", summary)
        self.assertIn("**Round:** initial review", summary)
        self.assertIn("**Outcome:** ✅ Approved", summary)

    def test_no_verdict_submitted(self):
        patches = _patch(
            pr_view=lambda repo, pr, fields: {"title": "", "headRefOid": "headsha"},
            reviews_by=lambda repo, pr, login: [Review(login, ReviewState.CHANGES_REQUESTED, "oldsha")],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(ReviewRun(99, "reviewer-app[bot]"), None)
        self.assertIn("**Round:** re-review (after 1 changes-requested)", summary)
        self.assertIn("**Outcome:** ⚠️ No verdict submitted — see the final message below.", summary)

    def test_first_ever_review_requesting_changes_is_initial_not_re_review(self):
        patches = _patch(
            pr_view=lambda repo, pr, fields: {"title": "", "headRefOid": "head1"},
            reviews_by=lambda repo, pr, login: [Review(login, ReviewState.CHANGES_REQUESTED, "head1")],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(ReviewRun(99, "reviewer-app[bot]"), None)
        self.assertIn("**Round:** initial review", summary)
        self.assertIn("**Outcome:** 🔴 Changes requested", summary)

    def test_a_genuine_re_review_counts_only_prior_commit_changes_requested(self):
        patches = _patch(
            pr_view=lambda repo, pr, fields: {"title": "", "headRefOid": "head2"},
            reviews_by=lambda repo, pr, login: [
                Review(login, ReviewState.CHANGES_REQUESTED, "head1"),
                Review(login, ReviewState.CHANGES_REQUESTED, "head2"),
            ],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(ReviewRun(99, "reviewer-app[bot]"), None)
        self.assertIn("**Round:** re-review (after 1 changes-requested)", summary)
        self.assertIn("**Outcome:** 🔴 Changes requested", summary)

    def test_a_stale_verdict_against_an_old_commit_is_not_counted_as_this_runs(self):
        patches = _patch(
            pr_view=lambda repo, pr, fields: {"title": "", "headRefOid": "newsha"},
            reviews_by=lambda repo, pr, login: [Review(login, ReviewState.CHANGES_REQUESTED, "oldsha")],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(ReviewRun(99, "reviewer-app[bot]"), None)
        self.assertIn("**Outcome:** ⚠️ No verdict submitted — see the final message below.", summary)


class RefinementSectionTests(unittest.TestCase):
    def test_a_failed_label_lookup_shows_outcome_unavailable_and_warns(self):
        def boom(*a, **k):
            raise gh.GhCommandError("rate limited")
        patches = _patch(issue_labels=boom)
        buf = io.StringIO()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch("sys.stderr", buf):
            summary = _build(RefinementRun(7), None)
        self.assertIn("Label lookup failed", summary)
        self.assertIn("warning:", buf.getvalue())

    def test_body_refined(self):
        patches = _patch(
            issue_view=lambda repo, issue, fields: {"title": "Vague idea"},
            issue_labels=lambda repo, issue: ["type:coding-task", "status:refined"],
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(RefinementRun(7), None)
        self.assertIn("## Refinement run", summary)
        self.assertIn("**Outcome:** Body refined", summary)

    def test_stopped_for_clarification(self):
        patches = _patch(issue_labels=lambda repo, issue: ["status:needs-attention"])
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(RefinementRun(7), None)
        self.assertIn("**Outcome:** ⚠️ Stopped for clarification — see the final message below.", summary)


class EstimationSectionTests(unittest.TestCase):
    def test_a_failed_label_lookup_shows_outcome_unavailable(self):
        def boom(*a, **k):
            raise gh.GhCommandError("rate limited")
        patches = _patch(issue_labels=boom)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
             patch("sys.stderr", io.StringIO()):
            summary = _build(EstimationRun(7), None)
        self.assertIn("Label lookup failed", summary)

    def test_estimate_posted_with_size_label(self):
        patches = _patch(issue_labels=lambda repo, issue: ["type:coding-task", "status:estimated", "size:M"])
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(EstimationRun(7), None)
        self.assertIn("**Outcome:** Estimate posted — `size:M`", summary)


class CostAndExecFileTests(unittest.TestCase):
    def test_missing_execution_file_yields_an_unknown_cost_and_a_placeholder_message(self):
        patches = _patch(issue_labels=lambda repo, issue: [])
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(RefinementRun(7), "/no/such/file")
        self.assertIn("**Cost:** $unknown", summary)
        self.assertIn("> _No final message — the run produced no result output._", summary)

    def test_missing_execution_file_reports_a_timeout(self):
        patches = _patch()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(RefinementRun(7), None, cost_warn=0.30)
        self.assertIn("killed (timed out) before writing results", summary)

    def test_cost_over_the_warn_limit_adds_a_warning_line(self, ):
        patches = _patch(issue_labels=lambda repo, issue: ["status:refined"])
        exec_file = self._write_exec({"total_cost_usd": 2.5, "result": "done"})
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(RefinementRun(7), exec_file, cost_warn=0.30)
        self.assertIn("⚠️ cost $2.5000 over the $0.30 warn limit", summary)

    def test_cost_under_the_warn_limit_adds_no_warning_line(self):
        patches = _patch(issue_labels=lambda repo, issue: ["status:refined"])
        exec_file = self._write_exec({"total_cost_usd": 0.10, "result": "done"})
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = _build(RefinementRun(7), exec_file, cost_warn=0.30)
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


def _ctx() -> ActionsCtx:
    return ActionsCtx(repo=REPO, token="", server_url=SERVER)


class PhaseArgumentTests(unittest.TestCase):
    def test_errors_on_an_unknown_phase(self):
        with self.assertRaisesRegex(ValueError, "unknown phase Bogus"):
            run_summary._parse_phase("Bogus")

    def test_a_phase_without_its_subject_is_an_error(self):
        for phase, kwargs in [
            (run_summary.Phase.CODER, dict(issue=None, pr=5)),
            (run_summary.Phase.REVIEW, dict(issue=7, pr=None)),
            (run_summary.Phase.REFINEMENT, dict(issue=None, pr=None)),
            (run_summary.Phase.ESTIMATION, dict(issue=None, pr=None)),
        ]:
            with self.subTest(phase=phase), self.assertRaisesRegex(ValueError, "is required"):
                run_summary._phase_run(phase, round_=None, ctx=_ctx(), **kwargs)


class ReviewerBotScopeTests(unittest.TestCase):
    def test_only_the_review_phase_requires_the_reviewer_bot(self):
        with patch.dict(os.environ, {}, clear=True):
            for phase in (run_summary.Phase.CODER, run_summary.Phase.REFINEMENT, run_summary.Phase.ESTIMATION):
                with self.subTest(phase=phase):
                    run_summary._phase_run(phase, issue=7, pr=None, round_=None, ctx=_ctx())

    def test_review_phase_fails_fast_without_the_reviewer_bot(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(cli.MissingEnvError):
            run_summary._phase_run(run_summary.Phase.REVIEW, issue=None, pr=5, round_=None, ctx=_ctx())

    def test_review_phase_uses_the_reviewer_bot_from_env(self):
        with patch.dict(os.environ, {"REVIEWER_BOT": "rev[bot]"}, clear=True):
            run = run_summary._phase_run(run_summary.Phase.REVIEW, issue=None, pr=5, round_=None, ctx=_ctx())
        self.assertEqual(run, run_summary.ReviewRun(5, "rev[bot]"))


class RoundLineTests(unittest.TestCase):
    def test_fix_with_a_count(self):
        self.assertEqual(run_summary._round_line(Round.FIX, 2), "Fix round 2")

    def test_fix_with_a_zero_count(self):
        self.assertEqual(run_summary._round_line(Round.FIX, 0), "Fix round 0")

    def test_fix_with_no_count(self):
        self.assertEqual(run_summary._round_line(Round.FIX, None), "Fix round")

    def test_initial(self):
        self.assertEqual(run_summary._round_line(Round.INITIAL, None), "Initial implementation")

    def test_no_round_is_blank(self):
        self.assertIsNone(run_summary._round_line(None, None))


class CliTests(unittest.TestCase):
    def test_writes_the_summary_to_github_step_summary(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = os.path.join(tmp, "summary.md")
            open(summary_path, "w").close()
            ctx = ActionsCtx(repo=REPO, token="", server_url=SERVER)
            env = {"GITHUB_RUN_ID": "42", "GITHUB_STEP_SUMMARY": summary_path}
            patches = _patch(issue_labels=lambda repo, issue: ["status:needs-attention"])
            with patch.dict(os.environ, env, clear=True), patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
                run_summary.main(ctx, ["--phase", "Refinement", "--issue", "7"])
            with open(summary_path) as f:
                content = f.read()
        self.assertIn("## Refinement run", content)
        self.assertIn("Stopped for clarification", content)


if __name__ == "__main__":
    unittest.main()
