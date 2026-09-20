#!/usr/bin/env bash
#
# Append pipeline-metrics records (extract-metrics.sh) to metrics.jsonl on the
# orphan `metrics` branch, one commit per call. The caller serialises appends
# with a concurrency group; on a losing push race this retries by re-fetching
# the branch tip and re-appending. The branch is created on first use.
#
# Usage: append-metrics.sh <record-file>...
#
# Env: GH_TOKEN (contents:write), GITHUB_REPOSITORY, GITHUB_SERVER_URL,
#      GITHUB_RUN_ID.
#
# pipeline/src/pipeline/append_metrics.py is the only place this logic lives
# (interns#159) -- this is a thin shim that shells out to it.

set -euo pipefail

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.append_metrics "$@"
