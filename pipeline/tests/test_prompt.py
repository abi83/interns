import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import cli, prompt


def _write(tmp_path: Path, name: str, content: bytes) -> str:
    path = tmp_path / name
    path.write_bytes(content)
    return str(path)


def _parse_github_output_value(block: bytes, name: bytes) -> bytes:
    """Mirrors GitHub Actions' own multiline-output parsing: everything
    between the `name<<DELIM` and closing `DELIM` lines, joined by the `\n`
    that separated them -- that separator is not part of the value."""
    lines = block.split(b"\n")
    prefix = name + b"<<"
    assert lines[0].startswith(prefix)
    delim = lines[0][len(prefix):]
    end = lines.index(delim, 1)
    return b"\n".join(lines[1:end])


class GithubOutputBlockTests(unittest.TestCase):
    def test_resamples_the_delimiter_when_it_collides_with_content(self):
        with patch("pipeline.cli.secrets.token_hex", side_effect=["deadbeef", "cafef00d"]):
            out = cli.github_output_block("text", b"line one\nghadelim_deadbeef\nline two\n")
        self.assertNotIn(b"text<<ghadelim_deadbeef\n", out)
        self.assertIn(b"text<<ghadelim_cafef00d\n", out)
        value = _parse_github_output_value(out, b"text")
        self.assertEqual(value, b"line one\nghadelim_deadbeef\nline two")

    def test_content_not_from_a_file_round_trips(self):
        out = cli.github_output_block("text", b"arbitrary in-memory content")
        self.assertEqual(_parse_github_output_value(out, b"text"), b"arbitrary in-memory content")


class BuildOutputTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_concatenates_files_in_order(self):
        a = _write(self.tmp_path, "a.md", b"first\n")
        b = _write(self.tmp_path, "b.md", b"second\n")
        out = prompt.build_output("text", [a, b])
        self.assertIn(b"first\nsecond\n", out)

    def test_wraps_in_a_github_output_heredoc_block(self):
        f = _write(self.tmp_path, "a.md", b"hello\n")
        out = prompt.build_output("text", [f])
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith(b"text<<"))
        delim = lines[0].removeprefix(b"text<<")
        self.assertEqual(lines[-1], delim)

    def test_content_ending_in_newline_parses_back_with_no_extra_blank_line(self):
        # Regression: naively joining as f"...{delim}\n{content}\n{delim}\n"
        # inserts a second newline before the closing delimiter when content
        # already ends in one. GitHub Actions only strips the single
        # newline immediately before the delimiter line, so that extra
        # newline would survive into the parsed value as a trailing blank
        # line -- every prompt would silently gain one on top of the
        # original bash version's behavior.
        f = _write(self.tmp_path, "a.md", b"hello world\n")
        out = prompt.build_output("text", [f])
        value = _parse_github_output_value(out, b"text")
        self.assertEqual(value, b"hello world")

    def test_content_not_ending_in_newline_still_closes_on_its_own_line(self):
        f = _write(self.tmp_path, "a.md", b"hello world")
        out = prompt.build_output("text", [f])
        value = _parse_github_output_value(out, b"text")
        self.assertEqual(value, b"hello world")

    def test_content_containing_the_heredoc_marker_does_not_break_output(self):
        # A prompt file that happens to contain a delimiter-shaped line must
        # not be able to truncate the block -- the delimiter is resampled
        # until it doesn't collide with the content.
        f = _write(self.tmp_path, "a.md", b"before\nghadelim_deadbeef\nafter\n")
        out = prompt.build_output("text", [f])
        lines = out.splitlines()
        delim = lines[0].removeprefix(b"text<<")
        self.assertNotEqual(delim, b"ghadelim_deadbeef")
        value = _parse_github_output_value(out, b"text")
        self.assertEqual(value, b"before\nghadelim_deadbeef\nafter")

    def test_content_with_bytes_invalid_in_utf8_is_passed_through_unchanged(self):
        # Bash's `cat` is encoding-agnostic; decoding here would crash the
        # step on a prompt file that isn't valid UTF-8.
        f = _write(self.tmp_path, "a.md", b"before \xff\xfe after\n")
        out = prompt.build_output("text", [f])
        value = _parse_github_output_value(out, b"text")
        self.assertEqual(value, b"before \xff\xfe after")


class CliTests(unittest.TestCase):
    def test_writes_to_github_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_file = _write(Path(tmpdir), "p.md", b"instructions\n")
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_bytes(b"")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}):
                prompt._main([prompt_file])
            contents = Path(output_file).read_bytes()
        self.assertIn(b"text<<", contents)
        self.assertIn(b"instructions\n", contents)

    def test_appends_rather_than_overwrites(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            prompt_file = _write(Path(tmpdir), "p.md", b"instructions\n")
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_bytes(b"existing=value\n")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}):
                prompt._main([prompt_file])
            contents = Path(output_file).read_bytes()
        self.assertTrue(contents.startswith(b"existing=value\n"))


if __name__ == "__main__":
    unittest.main()
