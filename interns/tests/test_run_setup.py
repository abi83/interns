import subprocess
import tempfile
import unittest
from pathlib import Path

from interns.steps import run_setup


class RunSetupTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _makefile(self, body: str):
        (self.root / "Makefile").write_text(body)

    def test_no_makefile_is_skipped(self):
        self.assertFalse(run_setup.run_setup(str(self.root)))

    def test_makefile_without_setup_target_is_skipped(self):
        self._makefile("test:\n\tpytest\n")
        self.assertFalse(run_setup.run_setup(str(self.root)))

    def test_stub_target_is_skipped(self):
        self._makefile('setup:\n\t@echo "INTERNS: not configured -- expected"\n')
        self.assertFalse(run_setup.run_setup(str(self.root)))

    def test_configured_target_runs_in_repo_root(self):
        self._makefile("setup:\n\ttouch ran\n")
        self.assertTrue(run_setup.run_setup(str(self.root)))
        self.assertTrue((self.root / "ran").exists())

    def test_failing_target_raises(self):
        self._makefile("setup:\n\texit 3\n")
        with self.assertRaises(subprocess.CalledProcessError):
            run_setup.run_setup(str(self.root))


if __name__ == "__main__":
    unittest.main()
