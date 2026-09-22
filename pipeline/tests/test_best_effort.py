import io
import unittest
from unittest.mock import patch

from pipeline import best_effort


class CallTests(unittest.TestCase):
    def test_returns_real_value_on_success(self):
        self.assertEqual(best_effort.call("reason", ValueError, int, "42"), 42)

    def test_returns_none_on_expected_error(self):
        with patch("sys.stderr", io.StringIO()):
            result = best_effort.call("reason", ValueError, int, "bad")
        self.assertIsNone(result)

    def test_warning_names_function_and_reason(self):
        buf = io.StringIO()
        with patch("sys.stderr", buf):
            best_effort.call("my reason", ValueError, int, "bad")
        warning = buf.getvalue()
        self.assertIn("my reason", warning)
        self.assertIn("int", warning)

    def test_propagates_unexpected_error(self):
        with self.assertRaises(TypeError):
            best_effort.call("reason", ValueError, int, None)

    def test_raises_on_empty_reason(self):
        with self.assertRaises(ValueError):
            best_effort.call("", ValueError, int, "42")

    def test_passes_args_and_kwargs(self):
        def concat(a, b, sep=""):
            return f"{a}{sep}{b}"
        self.assertEqual(best_effort.call("r", ValueError, concat, "x", "y", sep="-"), "x-y")
