import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interns.steps import check_build_config


class CliTests(unittest.TestCase):
    def test_writes_configured_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "Makefile").write_text("test:\n\tnpm test\n")
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}):
                check_build_config.main([tmpdir])
            self.assertEqual(Path(output_file).read_text(), "configured=true\n")

    def test_writes_configured_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}):
                check_build_config.main([tmpdir])
            self.assertEqual(Path(output_file).read_text(), "configured=false\n")


if __name__ == "__main__":
    unittest.main()
