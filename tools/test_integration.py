"""Integration tier: real entrypoints against fake `gh`/`git` executables.

    uv run --frozen python tools/test_integration.py [pytest args]

Entrypoints run as subprocesses, so each is wrapped in `coverage run` (see
testkit/harness.py). Fails when branch coverage drops below
`floors.integration` in pyproject.toml.
"""

import sys

from _tier import run_tier

if __name__ == "__main__":
    sys.exit(run_tier("integration", ["tests/integration", *sys.argv[1:]], {"INTERNS_COVERAGE": "1"}))
