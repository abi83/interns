import os
import tempfile
import unittest
from unittest.mock import patch

from pipeline import report_run


class FormatCostTests(unittest.TestCase):
    def test_formats_to_four_decimal_places(self):
        self.assertEqual(report_run.format_cost("0.42"), "0.4200")

    def test_none_is_unknown(self):
        self.assertEqual(report_run.format_cost(None), "unknown")

    def test_empty_string_is_unknown(self):
        self.assertEqual(report_run.format_cost(""), "unknown")


class ReportTests(unittest.TestCase):
    def test_comments_on_the_issue_with_the_parsed_cost(self):
        with patch("pipeline.report_run.execution.result_field", return_value="0.42"), \
             patch("pipeline.report_run.actions_env.run_url", return_value="https://x/runs/42"), \
             patch("pipeline.report_run.gh.issue_comment") as comment, \
             patch("pipeline.report_run.gh.pr_comment") as pr_comment:
            report_run.report("acme/widgets", "Coder", "exec.json", 55, None, None)
        comment.assert_called_once_with(
            "acme/widgets", 55,
            "Coder [pipeline run](https://x/runs/42) — cost: $0.4200",
        )
        pr_comment.assert_not_called()

    def test_falls_back_to_the_pr_only_when_the_issue_number_is_empty(self):
        with patch("pipeline.report_run.execution.result_field", return_value="1"), \
             patch("pipeline.report_run.actions_env.run_url", return_value="https://x/runs/1"), \
             patch("pipeline.report_run.gh.issue_comment") as comment, \
             patch("pipeline.report_run.gh.pr_comment") as pr_comment:
            report_run.report("acme/widgets", "Review", "exec.json", None, 88, None)
        pr_comment.assert_called_once()
        comment.assert_not_called()

    def test_missing_execution_file_yields_an_unknown_cost(self):
        with patch("pipeline.report_run.execution.result_field", return_value=None), \
             patch("pipeline.report_run.actions_env.run_url", return_value="https://x/runs/1"), \
             patch("pipeline.report_run.gh.issue_comment") as comment:
            report_run.report("acme/widgets", "Coder", "/no/such/file", 55, None, None)
        self.assertIn("cost: $unknown", comment.call_args[0][2])

    def test_a_malformed_execution_file_yields_an_unknown_cost_not_a_crash(self):
        # Regression: execution.result_field used to be called unguarded here,
        # so a present-but-truncated exec file (partial write, disk pressure)
        # raised json.JSONDecodeError instead of falling back like a missing
        # file does. The fix lives in execution.result_field itself, not a
        # local guard -- this exercises the real function, not a mock.
        with tempfile.TemporaryDirectory() as tmp:
            exec_file = os.path.join(tmp, "exec.json")
            with open(exec_file, "w") as f:
                f.write("")
            with patch("pipeline.report_run.actions_env.run_url", return_value="https://x/runs/1"), \
                 patch("pipeline.report_run.gh.issue_comment") as comment:
                report_run.report("acme/widgets", "Coder", exec_file, 55, None, None)
        self.assertIn("cost: $unknown", comment.call_args[0][2])

    def test_errors_when_given_neither_an_issue_nor_a_pr(self):
        with patch("pipeline.report_run.execution.result_field", return_value=None), \
             patch("pipeline.report_run.actions_env.run_url", return_value="https://x/runs/1"):
            with self.assertRaises(ValueError):
                report_run.report("acme/widgets", "Coder", "exec.json", None, None, None)

    def test_warn_appends_a_warning_line_to_the_same_comment(self):
        with patch("pipeline.report_run.execution.result_field", return_value="0.42"), \
             patch("pipeline.report_run.actions_env.run_url", return_value="https://x/runs/1"), \
             patch("pipeline.report_run.gh.issue_comment") as comment:
            report_run.report("acme/widgets", "Coder", "exec.json", 55, None,
                               "tests aren't configured")
        body = comment.call_args[0][2]
        self.assertIn("cost: $0.4200", body)
        self.assertIn("⚠️ tests aren't configured", body)

    def test_no_warn_adds_no_warning_line(self):
        with patch("pipeline.report_run.execution.result_field", return_value="0.42"), \
             patch("pipeline.report_run.actions_env.run_url", return_value="https://x/runs/1"), \
             patch("pipeline.report_run.gh.issue_comment") as comment:
            report_run.report("acme/widgets", "Coder", "exec.json", 55, None, None)
        self.assertNotIn("⚠️", comment.call_args[0][2])


class CliTests(unittest.TestCase):
    def test_parses_positional_and_warn_flag(self):
        with patch("pipeline.report_run.report") as report_fn, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}):
            report_run._main(["Coder", "exec.json", "55", "", "--warn", "watch out"])
        report_fn.assert_called_once_with(
            "acme/widgets", "Coder", "exec.json", 55, None, "watch out",
        )

    def test_empty_issue_and_pr_are_none(self):
        with patch("pipeline.report_run.report") as report_fn, \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "acme/widgets"}):
            report_run._main(["Coder", "exec.json"])
        report_fn.assert_called_once_with(
            "acme/widgets", "Coder", "exec.json", None, None, None,
        )


if __name__ == "__main__":
    unittest.main()
