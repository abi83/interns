"""`.github/interns.schema.json` and the config loader's known keys must agree."""

import json
from pathlib import Path

from pipeline import config

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / ".github/interns.schema.json").read_text())
PROPERTIES = SCHEMA["properties"]


def test_top_level_keys():
    assert set(PROPERTIES) == set(config.KNOWN_TOP_KEYS)


def test_agents():
    assert set(PROPERTIES["agents"]["properties"]) == set(config.KNOWN_AGENTS)


def test_limit_keys():
    assert set(SCHEMA["definitions"]["limits"]["properties"]) == set(config.KNOWN_LIMIT_KEYS)


def test_wiki_keys():
    assert set(PROPERTIES["wiki"]["properties"]) == set(config.KNOWN_WIKI_KEYS)


def test_agent_and_defaults_blocks_use_the_limits_definition():
    blocks = [PROPERTIES["defaults"], *PROPERTIES["agents"]["properties"].values()]
    assert all(block == {"$ref": "#/definitions/limits"} for block in blocks)
