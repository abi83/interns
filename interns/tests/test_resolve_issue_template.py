import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interns import resolve_issue_template


class HeadingsTests(unittest.TestCase):
    def test_strips_frontmatter_and_keeps_only_headings(self):
        text = "---\nlabels: type:bug\n---\n## Description\ntext here\n## Impact\n"
        self.assertEqual(resolve_issue_template.headings(text), ["## Description", "## Impact"])

    def test_html_comments_are_dropped_as_a_side_effect_of_the_heading_filter(self):
        text = "## Question to Answer\n<!-- guidance -->\nsome text\n"
        self.assertEqual(resolve_issue_template.headings(text), ["## Question to Answer"])

    def test_no_frontmatter_is_fine(self):
        text = "## Question to Answer\n"
        self.assertEqual(resolve_issue_template.headings(text), ["## Question to Answer"])

    def test_unclosed_frontmatter_yields_no_headings(self):
        # Matches the original awk: once the frontmatter state opens it never
        # closes without a matching `---`, so every remaining line -- real
        # headings included -- is treated as still inside it and dropped.
        text = "---\nlabels: type:bug\n## Description\n## Impact\n"
        self.assertEqual(resolve_issue_template.headings(text), [])


class BuildSkeletonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.builtin = Path(self.tmp.name) / "builtin"
        self.consumer = Path(self.tmp.name) / "consumer"
        self.builtin.mkdir()
        self.consumer.mkdir()
        (self.builtin / "coding-task.md").write_text(
            "---\nlabels: type:coding-task\n---\n## Value\n<!-- why -->\n## Scope\n")
        (self.builtin / "bug.md").write_text(
            "---\nlabels: type:bug\n---\n## Description\n## Impact\n")
        (self.builtin / "spike.md").write_text("## Question to Answer\n")

    def test_emits_a_heading_only_block_per_type_frontmatter_and_comments_gone(self):
        skeleton = resolve_issue_template.build_skeleton(
            self.builtin, self.consumer, ["coding-task", "bug", "spike"])
        self.assertIn("type:coding-task\n## Value\n## Scope", skeleton)
        self.assertIn("type:bug\n## Description\n## Impact", skeleton)
        self.assertNotIn("---", skeleton)
        self.assertNotIn("<!--", skeleton)

    def test_consumer_override_wins_when_present(self):
        (self.consumer / "bug.md").write_text("---\nlabels: type:bug\n---\n## Custom\n## Fields\n")
        skeleton = resolve_issue_template.build_skeleton(self.builtin, self.consumer, ["bug"])
        self.assertIn("## Custom", skeleton)
        self.assertNotIn("## Description", skeleton)

    def test_fails_when_a_type_has_no_template_anywhere(self):
        (self.builtin / "spike.md").unlink()
        with self.assertRaises(resolve_issue_template.NoTemplateError) as ctx:
            resolve_issue_template.build_skeleton(self.builtin, self.consumer, ["spike"])
        self.assertIn("no template for 'spike'", str(ctx.exception))


class CliTests(unittest.TestCase):
    def test_writes_the_skeleton_block_to_github_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            builtin = Path(tmp) / "builtin"
            builtin.mkdir()
            (builtin / "spike.md").write_text("## Question to Answer\n")
            output_file = Path(tmp) / "output"
            output_file.write_text("")

            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_file)}):
                resolve_issue_template._main(
                    ["--builtin-dir", str(builtin), "--consumer-dir", str(Path(tmp) / "consumer"),
                     "--types", "spike"])

            content = output_file.read_text()
        self.assertRegex(content, r"^skeleton<<ghadelim_\w+\n")
        self.assertIn("type:spike\n## Question to Answer", content)

    def test_defaults_types_and_consumer_dir(self):
        with patch("interns.resolve_issue_template.build_skeleton", return_value="") as build, \
             patch.dict(os.environ, {"GITHUB_OUTPUT": "/dev/null"}):
            resolve_issue_template._main(["--builtin-dir", "/tmp/builtin"])
        args = build.call_args[0]
        self.assertEqual(str(args[1]), ".github/ISSUE_TEMPLATE")
        self.assertEqual(args[2], ["coding-task", "bug", "spike"])


if __name__ == "__main__":
    unittest.main()
