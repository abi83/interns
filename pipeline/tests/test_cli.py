import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import cli


class RequireEnvTests(unittest.TestCase):
    def test_returns_value(self):
        with patch.dict(os.environ, {"X": "v"}):
            self.assertEqual(cli.require_env("X"), "v")

    def test_unset_and_empty_raise_clear_error(self):
        for env in ({}, {"X": ""}):
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(cli.MissingEnvError, "X unset"):
                    cli.require_env("X")


class OptionalIntTests(unittest.TestCase):
    def test_conversions(self):
        self.assertIsNone(cli.optional_int(""))
        self.assertEqual(cli.optional_int("12"), 12)


class WriteOutputTests(unittest.TestCase):
    def test_appends_bools_and_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            out.write_text("")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}):
                cli.write_output("a", True)
                cli.write_output("b", False)
                cli.write_output("c", "x y")
            self.assertEqual(out.read_text(), "a=true\nb=false\nc=x y\n")

    def test_requires_github_output(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(cli.MissingEnvError, "GITHUB_OUTPUT unset"):
                cli.write_output("a", True)


if __name__ == "__main__":
    unittest.main()
