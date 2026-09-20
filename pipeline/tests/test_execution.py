import json
import unittest
from unittest.mock import patch

from pipeline import execution


def _write(tmp_path, entries) -> str:
    path = tmp_path / "exec.json"
    path.write_text(json.dumps(entries))
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


class CliTests(unittest.TestCase):
    def test_prints_empty_string_when_no_value(self):
        with patch("pipeline.execution.result_field", return_value=None), \
             patch("builtins.print") as mock_print:
            execution._main(["/no/such/file", "total_cost_usd"])
        mock_print.assert_called_once_with("")

    def test_prints_the_value(self):
        with patch("pipeline.execution.result_field", return_value="0.5"), \
             patch("builtins.print") as mock_print:
            execution._main(["exec.json", "total_cost_usd"])
        mock_print.assert_called_once_with("0.5")


if __name__ == "__main__":
    unittest.main()
