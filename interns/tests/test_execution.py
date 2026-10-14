import unittest

from interns import execution
from testkit.execution_log import jsonl


def _write(tmp_path, entries) -> str:
    path = tmp_path / "exec.json"
    path.write_text(jsonl(entries))
    return str(path)


class ResultFieldTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_reads_a_field_from_the_result_entry(self):
        exec_file = _write(self.tmp_path, [{"type": "result", "total_cost_usd": 0.5}])
        self.assertEqual(execution.result_field(exec_file, "total_cost_usd"), "0.5")

    def test_missing_exec_file_argument_is_none(self):
        self.assertIsNone(execution.result_field(None, "total_cost_usd"))
        self.assertIsNone(execution.result_field("", "total_cost_usd"))

    def test_exec_file_that_does_not_exist_is_none(self):
        self.assertIsNone(execution.result_field(str(self.tmp_path / "missing.json"), "total_cost_usd"))

    def test_malformed_json_is_none(self):
        exec_file = self.tmp_path / "exec.json"
        exec_file.write_text("")
        self.assertIsNone(execution.result_field(str(exec_file), "total_cost_usd"))

    def test_truncated_json_is_none(self):
        exec_file = self.tmp_path / "exec.json"
        exec_file.write_text('[{"type": "result", "total')
        self.assertIsNone(execution.result_field(str(exec_file), "total_cost_usd"))

    def test_reads_a_jsonl_stream(self):
        exec_file = self.tmp_path / "exec.jsonl"
        exec_file.write_text('{"type": "system"}\n{"type": "result", "total_cost_usd": 0.25}\n')
        self.assertEqual(execution.result_field(str(exec_file), "total_cost_usd"), "0.25")
        self.assertEqual([e["type"] for e in execution.events(str(exec_file))], ["system", "result"])

    def test_truncated_jsonl_is_none(self):
        exec_file = self.tmp_path / "exec.jsonl"
        exec_file.write_text('{"type": "system"}\n{"type": "result", "tot')
        self.assertIsNone(execution.result_field(str(exec_file), "total_cost_usd"))

    def test_no_result_entry_is_none(self):
        exec_file = _write(self.tmp_path, [{"type": "assistant", "message": "hi"}])
        self.assertIsNone(execution.result_field(exec_file, "total_cost_usd"))

    def test_field_absent_on_the_result_entry_is_none(self):
        exec_file = _write(self.tmp_path, [{"type": "result"}])
        self.assertIsNone(execution.result_field(exec_file, "total_cost_usd"))

    def test_empty_string_field_value_is_none(self):
        exec_file = _write(self.tmp_path, [{"type": "result", "result": ""}])
        self.assertIsNone(execution.result_field(exec_file, "result"))

    def test_picks_the_first_result_entry(self):
        exec_file = _write(self.tmp_path, [
            {"type": "result", "num_turns": 3},
            {"type": "result", "num_turns": 9},
        ])
        self.assertEqual(execution.result_field(exec_file, "num_turns"), "3")


if __name__ == "__main__":
    unittest.main()
