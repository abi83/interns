import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import check_build_config


class IsConfiguredTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_no_makefile_is_not_configured(self):
        self.assertFalse(check_build_config.is_configured(str(self.tmp_path)))

    def test_makefile_with_marker_is_not_configured(self):
        (self.tmp_path / "Makefile").write_text(
            'test:\n\t@echo "INTERNS: not configured -- no tests configured"\n'
        )
        self.assertFalse(check_build_config.is_configured(str(self.tmp_path)))

    def test_makefile_without_marker_is_configured(self):
        (self.tmp_path / "Makefile").write_text("test:\n\tnpm test\n\nbuild:\n\tnpm run build\n")
        self.assertTrue(check_build_config.is_configured(str(self.tmp_path)))


class CliTests(unittest.TestCase):
    def test_writes_configured_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "Makefile").write_text("test:\n\tnpm test\n")
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}):
                check_build_config._main([tmpdir])
            self.assertEqual(Path(output_file).read_text(), "configured=true\n")

    def test_writes_configured_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "output")
            Path(output_file).write_text("")
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output_file}):
                check_build_config._main([tmpdir])
            self.assertEqual(Path(output_file).read_text(), "configured=false\n")


if __name__ == "__main__":
    unittest.main()
