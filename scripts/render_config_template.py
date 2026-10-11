"""Renders the consumer-facing templates/config/interns.yml from
templates/config/defaults.yml: identical, but every key commented out."""

from __future__ import annotations

from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parents[1] / "templates" / "config"
DEFAULTS_PATH = CONFIG_DIR / "defaults.yml"
TEMPLATE_PATH = CONFIG_DIR / "interns.yml"

HEADER = """\
# interns pipeline config -- every key below is commented out and shows
# interns' current default. Interns applies these defaults when a key is
# absent, so they track interns releases. Uncomment (with its parent keys) only
# what you deliberately want to override.
# Schema: abi83/interns/.github/interns.schema.json
"""


def render(defaults_text: str) -> str:
    body = defaults_text.split("\n\n", 1)[1]
    commented = [f"# {line}" if line and not line.startswith("#") else line for line in body.splitlines()]
    return HEADER + "\n" + "\n".join(commented) + "\n"


if __name__ == "__main__":
    TEMPLATE_PATH.write_text(render(DEFAULTS_PATH.read_text()))
