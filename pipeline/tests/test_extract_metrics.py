import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import extract_metrics

EXEC_EVENTS = [
    {"type": "system", "subtype": "init", "session_id": "sess-1"},
    {"type": "assistant", "isSidechain": False, "message": {"role": "assistant", "content": [
        {"type": "text", "text": "hi"},
        {"type": "tool_use", "name": "Read", "input": {}},
        {"type": "tool_use", "name": "Bash", "input": {}},
    ]}},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Bash", "input": {}},
        {"type": "tool_use", "name": "Task", "input": {}},
    ]}},
    {"type": "assistant", "isSidechain": True, "message": {"role": "assistant", "content": [
        {"type": "tool_use", "name": "Grep", "input": {}},
    ]}},
    {"type": "result", "subtype": "success", "session_id": "sess-1", "num_turns": 7,
     "duration_ms": 812345, "duration_api_ms": 431200, "total_cost_usd": 0.42,
     "modelUsage": {
         "claude-sonnet-5": {"inputTokens": 12000, "outputTokens": 48000,
                              "cacheReadInputTokens": 980000, "cacheCreationInputTokens": 60000,
                              "costUSD": 0.4},
         "claude-haiku-4-5": {"inputTokens": 300000, "outputTokens": 12000, "costUSD": 0.02},
     }},
]


class BuildRecordTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.exec_file = Path(self._tmpdir.name) / "exec.json"
        self.exec_file.write_text(json.dumps(EXEC_EVENTS))

    def tearDown(self):
        self._tmpdir.cleanup()

    def _build(self, **overrides):
        kwargs = dict(job="coder", issue=117, pr=128, repo="owner/repo",
                      run_id=42, run_attempt=2)
        kwargs.update(overrides)
        return extract_metrics.build_record(str(self.exec_file), **kwargs)

    def test_core_run_fields(self):
        record = self._build()
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["repo"], "owner/repo")
        self.assertEqual(record["run_id"], 42)
        self.assertEqual(record["run_attempt"], 2)
        self.assertEqual(record["job"], "coder")
        self.assertEqual(record["issue"], 117)
        self.assertEqual(record["pr"], 128)
        self.assertEqual(record["session_id"], "sess-1")
        self.assertEqual(record["agent_result"], "success")
        self.assertEqual(record["num_turns"], 7)
        self.assertEqual(record["duration_ms"], 812345)
        self.assertEqual(record["duration_api_ms"], 431200)

    def test_nests_per_model_usage_sub_agent_models_included_snake_cased(self):
        record = self._build()
        self.assertEqual(sorted(record["models"]), ["claude-haiku-4-5", "claude-sonnet-5"])
        self.assertEqual(record["models"]["claude-sonnet-5"]["cache_read_tokens"], 980000)
        self.assertEqual(record["models"]["claude-sonnet-5"]["cost_usd"], 0.4)
        self.assertEqual(record["models"]["claude-haiku-4-5"]["cache_read_tokens"], 0)

    def test_counts_main_agent_tool_use_blocks_only_grouped_by_name(self):
        record = self._build()
        self.assertEqual(record["tool_calls"], {"Read": 1, "Bash": 2, "Task": 1})

    def test_empty_issue_and_pr_become_null(self):
        record = self._build(job="refiner", issue=None, pr=None)
        self.assertIsNone(record["issue"])
        self.assertIsNone(record["pr"])
        self.assertEqual(record["job"], "refiner")

    def test_no_result_event_raises(self):
        no_result = Path(self._tmpdir.name) / "noresult.json"
        no_result.write_text(json.dumps([{"type": "system"}]))
        with self.assertRaises(extract_metrics.NoResultEventError):
            extract_metrics.build_record(str(no_result), job="coder", issue=None, pr=None,
                                          repo="owner/repo", run_id=42, run_attempt=1)

    def test_malformed_json_raises_no_result_event_not_json_decode_error(self):
        truncated = Path(self._tmpdir.name) / "truncated.json"
        truncated.write_text('[{"type":"system"')
        with self.assertRaises(extract_metrics.NoResultEventError):
            extract_metrics.build_record(str(truncated), job="coder", issue=None, pr=None,
                                          repo="owner/repo", run_id=42, run_attempt=1)


class NumOrNullTests(unittest.TestCase):
    def test_digits_parse(self):
        self.assertEqual(extract_metrics._num_or_null("117"), 117)

    def test_empty_and_non_digits_become_none(self):
        self.assertIsNone(extract_metrics._num_or_null(""))
        self.assertIsNone(extract_metrics._num_or_null("abc"))
        self.assertIsNone(extract_metrics._num_or_null("-1"))


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.exec_file = Path(self._tmpdir.name) / "exec.json"
        self.exec_file.write_text(json.dumps(EXEC_EVENTS))
        self._env = patch.dict(os.environ, {
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_RUN_ID": "42",
            "GITHUB_RUN_ATTEMPT": "2",
        })
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmpdir.cleanup()

    def _run_capture(self, argv):
        import io
        import contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = extract_metrics._main(argv)
        return status, out.getvalue()

    def test_emits_one_line_with_core_run_fields(self):
        status, out = self._run_capture([str(self.exec_file), "--job", "coder",
                                          "--issue", "117", "--pr", "128"])
        self.assertEqual(status, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["run_id"], 42)
        self.assertEqual(record["run_attempt"], 2)

    def test_rejects_an_unknown_job(self):
        with self.assertRaises(SystemExit):
            self._run_capture([str(self.exec_file), "--job", "nope"])

    def test_fails_when_the_execution_file_has_no_result_event(self):
        no_result = Path(self._tmpdir.name) / "noresult.json"
        no_result.write_text(json.dumps([{"type": "system"}]))
        status, out = self._run_capture([str(no_result), "--job", "coder"])
        self.assertNotEqual(status, 0)
        self.assertEqual(out, "")

    def test_fails_when_the_execution_file_is_missing(self):
        status, out = self._run_capture(["/no/such/file", "--job", "coder"])
        self.assertNotEqual(status, 0)
        self.assertEqual(out, "")

    def test_missing_github_repository_fails_cleanly_not_a_traceback(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.dict(os.environ, {"GITHUB_RUN_ID": "42"}):
            status, out = self._run_capture([str(self.exec_file), "--job", "coder"])
        self.assertEqual(status, 1)
        self.assertEqual(out, "")

    def test_missing_github_run_id_fails_cleanly_not_a_traceback(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/repo"}):
            status, out = self._run_capture([str(self.exec_file), "--job", "coder"])
        self.assertEqual(status, 1)
        self.assertEqual(out, "")


if __name__ == "__main__":
    unittest.main()
