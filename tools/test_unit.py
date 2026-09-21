"""Unit tier: pure logic, contract fixtures and mechanical guards.

    uv run --frozen python tools/test_unit.py [pytest args]

Fails when branch coverage drops below `floors.unit` in pyproject.toml.
"""

import sys

from _tier import run_tier

if __name__ == "__main__":
    sys.exit(run_tier("unit", ["--ignore=tests/integration", *sys.argv[1:]]))
