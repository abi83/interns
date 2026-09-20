import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import prompt


def _write(tmp_path: Path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content)
    return str(path)


class BuildOutputTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_concatenates_files_in_order(self):
        a = _write(self.tmp_path, "a.md", "first\n")
        b = _write(self.tmp_path, "b.md", "second\n")
        out = prompt.build_output("text", [a, b])
        self.assertIn("first\nsecond\n", out)

    def test_wraps_in_a_github_output_heredoc_block(self):
        f = _write(self.tmp_path, "a.md", "hello\n")
        out = prompt.build_output("text", [f])
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("text<<"))
        delim = lines[0].removeprefix("text<<")
        self.assertEqual(lines[-1], delim)

    def test_content_containing_the_heredoc_marker_does_not_break_output(self):
        # A prompt file that happens to contain a delimiter-shaped line must
        # not be able to truncate the block -- the delimiter is resampled
        # until it doesn't collide with the content.
        f = _write(self.tmp_path, "a.md", "before\nghadelim_deadbeef\nafter\n")
        out = prompt.build_output("text", [f])
        lines = out.splitlines()
        delim = lines[0].removeprefix("text<<")
        self.assertNotEqual(delim, "ghadelim_deadbeef")
        self.assertEqual(lines[-1], delim)
        body = "\n".join(lines[1:-1])
        self.assertEqual(body, "before\nghadelim_deadbeef\nafter\n")


class CliTests(unittest.TestCase):
    def test_writes_to_github_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_file = _write(Path(tmpdir), "p.md", "instructions\n")
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}):
                prompt._main([prompt_file])
            contents = Path(output_file).read_text()
        self.assertIn("text<<", contents)
        self.assertIn("instructions\n", contents)

    def test_appends_rather_than_overwrites(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_file = _write(Path(tmpdir), "p.md", "instructions\n")
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("existing=value\n")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}):
                prompt._main([prompt_file])
            contents = Path(output_file).read_text()
        self.assertTrue(contents.startswith("existing=value\n"))


if __name__ == "__main__":
    unittest.main()
