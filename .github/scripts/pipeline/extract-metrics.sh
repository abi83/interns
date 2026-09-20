#!/usr/bin/env bash
#
# Parse one claude-code-action execution file into a single pipeline-metrics
# record (one JSON object) on stdout, for append-metrics.sh to persist.
#
# Usage: extract-metrics.sh <execution-file> --job <job> [--issue N] [--pr N]
#
# Bump SCHEMA_VERSION (pipeline/src/pipeline/extract_metrics.py) and
# .github/pipeline-metrics.schema.json together on any breaking shape
# change. Exits non-zero, printing nothing, when the file is missing or has
# no result event (a killed run can leave a truncated file).
#
# pipeline/src/pipeline/extract_metrics.py is the only place this logic
# lives (interns#159) -- this is a thin shim that shells out to it.

set -euo pipefail

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.extract_metrics "$@"
