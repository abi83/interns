import runpy
import unittest
from unittest import mock


class MainModuleTests(unittest.TestCase):
    def test_exits_with_cli_return_code(self):
        with mock.patch("interns_install.cli.main", return_value=3):
            with self.assertRaises(SystemExit) as ctx:
                runpy.run_module("interns_install", run_name="__main__")
        self.assertEqual(ctx.exception.code, 3)


if __name__ == "__main__":
    unittest.main()
