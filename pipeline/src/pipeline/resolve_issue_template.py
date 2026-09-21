"""Resolve the section skeleton the refiner rewrites an issue body into, in
code rather than by globbing paths in the prompt. For each refineable issue
type it picks one template -- the consumer repo's
`.github/ISSUE_TEMPLATE/<type>.md` when present, otherwise the built-in
`templates/issue/<type>.md` -- drops the YAML frontmatter and HTML comments,
and emits the headings in order. The refiner picks the type, then rewrites
into the matching block; it never resolves a path itself.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from . import cli, prompt

HEADING_RE = re.compile(r"^#{1,6} .*$")

DEFAULT_TYPES = ["coding-task", "bug", "spike"]


class NoTemplateError(ValueError):
    pass


def headings(text: str) -> list[str]:
    """Markdown heading lines, with the leading YAML frontmatter block
    stripped. HTML comments in these templates never start with `#`, so
    filtering to heading lines drops them for free.

    An opened-but-never-closed frontmatter block (missing the closing `---`)
    yields no headings at all, matching the original awk script: it never
    leaves the frontmatter state, so every remaining line -- headings
    included -- gets skipped."""
    lines = text.splitlines()
    if lines and lines[0] == "---":
        end = next((i for i in range(1, len(lines)) if lines[i] == "---"), None)
        if end is None:
            return []
        lines = lines[end + 1:]
    return [line for line in lines if HEADING_RE.match(line)]


def resolve_template(template_type: str, builtin_dir: Path, consumer_dir: Path) -> Path:
    override = consumer_dir / f"{template_type}.md"
    if override.is_file():
        return override
    builtin = builtin_dir / f"{template_type}.md"
    if builtin.is_file():
        return builtin
    raise NoTemplateError(f"resolve-issue-template: no template for '{template_type}'")


def build_skeleton(builtin_dir: Path, consumer_dir: Path, types: list[str]) -> str:
    blocks = []
    for template_type in types:
        template = resolve_template(template_type, builtin_dir, consumer_dir)
        lines = [f"type:{template_type}", *headings(template.read_text()), ""]
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def _main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m pipeline.resolve_issue_template")
    parser.add_argument("--builtin-dir", required=True)
    parser.add_argument("--consumer-dir", default=".github/ISSUE_TEMPLATE")
    parser.add_argument("--types", default=" ".join(DEFAULT_TYPES))
    args = parser.parse_args(argv)

    skeleton = build_skeleton(Path(args.builtin_dir), Path(args.consumer_dir), args.types.split())

    cli.append_output(cli.github_output_block("skeleton", skeleton.encode()))
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(_main))
