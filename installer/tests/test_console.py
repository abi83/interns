import io
import unittest
from unittest import mock

from interns_install.console import Console


class ConfirmTests(unittest.TestCase):
    def test_assume_yes_short_circuits_without_reading_input(self):
        con = Console(assume_yes=True)
        with mock.patch("builtins.input") as input_:
            self.assertTrue(con.confirm("Proceed?"))
        input_.assert_not_called()

    def test_blank_answer_returns_default(self):
        con = Console()
        with mock.patch("builtins.input", return_value=""):
            self.assertFalse(con.confirm("Proceed?", default=False))
            self.assertTrue(con.confirm("Proceed?", default=True))

    def test_yes_variants_return_true(self):
        con = Console()
        for answer in ("y", "Y", "yes", "YES"):
            with mock.patch("builtins.input", return_value=answer):
                self.assertTrue(con.confirm("Proceed?", default=False))

    def test_other_answer_returns_false(self):
        con = Console()
        with mock.patch("builtins.input", return_value="n"):
            self.assertFalse(con.confirm("Proceed?", default=True))

    def test_eof_returns_default(self):
        con = Console()
        with mock.patch("builtins.input", side_effect=EOFError()):
            self.assertEqual(con.confirm("Proceed?", default=True), True)
            self.assertEqual(con.confirm("Proceed?", default=False), False)


class PromptTests(unittest.TestCase):
    def test_returns_stripped_input(self):
        con = Console()
        with mock.patch("builtins.input", return_value="  acme/widgets  "):
            self.assertEqual(con.prompt("Repo?"), "acme/widgets")


class PromptSecretTests(unittest.TestCase):
    def test_uses_getpass_and_strips(self):
        con = Console()
        with mock.patch("interns_install.console.getpass.getpass", return_value="  s3cr3t  ") as gp:
            self.assertEqual(con.prompt_secret("Token?"), "s3cr3t")
        gp.assert_called_once_with("Token? ")


class MutationTests(unittest.TestCase):
    def test_live_run_records_and_returns_true(self):
        con = Console(dry_run=False)
        self.assertTrue(con.mutation("set secret X"))
        self.assertEqual(con.planned, ["set secret X"])

    def test_dry_run_records_and_returns_false(self):
        con = Console(dry_run=True)
        self.assertFalse(con.mutation("set secret X"))
        self.assertEqual(con.planned, ["set secret X"])


class SummaryTests(unittest.TestCase):
    def test_nothing_to_do_when_no_mutations(self):
        con = Console()
        with mock.patch("builtins.print") as p:
            con.summary()
        output = "\n".join(str(c.args[0]) if c.args else "" for c in p.call_args_list)
        self.assertIn("Nothing to do.", output)

    def test_planned_label_for_dry_run(self):
        con = Console(dry_run=True)
        con.mutation("set secret X")
        with mock.patch("builtins.print") as p:
            con.summary()
        output = "\n".join(str(c.args[0]) if c.args else "" for c in p.call_args_list)
        self.assertIn("Would perform:", output)
        self.assertIn("set secret X", output)

    def test_done_label_for_live_run(self):
        con = Console(dry_run=False)
        con.mutation("set secret X")
        with mock.patch("builtins.print") as p:
            con.summary()
        output = "\n".join(str(c.args[0]) if c.args else "" for c in p.call_args_list)
        self.assertIn("Done:", output)

    def test_manual_items_listed_separately(self):
        con = Console()
        con.note_manual("install the GitHub App")
        with mock.patch("builtins.print") as p:
            con.summary()
        output = "\n".join(str(c.args[0]) if c.args else "" for c in p.call_args_list)
        self.assertIn("Still manual:", output)
        self.assertIn("install the GitHub App", output)


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
