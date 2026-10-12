import tempfile
import unittest
from pathlib import Path

from interns.domain import build_config


class IsConfiguredTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_no_makefile_is_not_configured(self):
        self.assertFalse(build_config.is_configured(str(self.tmp_path)))

    def test_makefile_with_marker_is_not_configured(self):
        (self.tmp_path / "Makefile").write_text(
            'test:\n\t@echo "INTERNS: not configured -- no tests configured"\n'
        )
        self.assertFalse(build_config.is_configured(str(self.tmp_path)))

    def test_makefile_without_marker_is_configured(self):
        (self.tmp_path / "Makefile").write_text("test:\n\tnpm test\n\nbuild:\n\tnpm run build\n")
        self.assertTrue(build_config.is_configured(str(self.tmp_path)))

    def test_makefile_with_bytes_invalid_in_utf8_does_not_crash(self):
        # Bash's `grep -F` is encoding-agnostic; decoding here would crash
        # the step on a Makefile that isn't valid UTF-8.
        (self.tmp_path / "Makefile").write_bytes(b"test:\n\t@echo \xff\xfe ok\n")
        self.assertTrue(build_config.is_configured(str(self.tmp_path)))


if __name__ == "__main__":
    unittest.main()
