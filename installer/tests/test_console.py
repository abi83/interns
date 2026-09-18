import io
import unittest
from unittest import mock

from interns_install.console import Console


class PromptMultilineSecretTests(unittest.TestCase):
    def _run(self, stdin_text: str) -> str:
        con = Console()
        with mock.patch("sys.stdin", io.StringIO(stdin_text)):
            return con.prompt_multiline_secret("Paste a key")

    def test_blank_line_skips(self):
        self.assertEqual(self._run("\n"), "")

    def test_stops_at_end_marker_without_needing_eof(self):
        pem = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "abc123\n"
            "def456\n"
            "-----END RSA PRIVATE KEY-----\n"
        )
        # Trailing junk after the END marker (e.g. a stray extra Enter) must
        # not be required for the read to complete.
        self.assertEqual(self._run(pem + "\n"), pem.strip())

    def test_eof_without_end_marker_still_returns_what_was_read(self):
        partial = "-----BEGIN RSA PRIVATE KEY-----\nabc123"
        self.assertEqual(self._run(partial), partial.strip())


if __name__ == "__main__":
    unittest.main()
