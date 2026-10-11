"""The installed templates/config/interns.yml is generated from defaults.yml."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("render_config_template", ROOT / "scripts" / "render_config_template.py")
render_config_template = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render_config_template)


def test_consumer_template_is_rendered_from_defaults():
    expected = render_config_template.render(render_config_template.DEFAULTS_PATH.read_text())
    assert render_config_template.TEMPLATE_PATH.read_text() == expected, (
        "run `python3 scripts/render_config_template.py`"
    )


def test_consumer_template_has_no_active_keys():
    active = [
        line for line in render_config_template.TEMPLATE_PATH.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert active == []
