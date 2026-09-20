#!/usr/bin/env bash
#
# A red PR check goes straight to a human, no coder retry loop (#133).
#
# Usage: route-red-checks.sh <pr> <issue-or-empty> <reason>
#
# pipeline/src/pipeline/route_red_checks.py is the only place this logic
# lives (interns#159) -- this is a thin shim that shells out to it.

set -euo pipefail

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.route_red_checks "$@"
