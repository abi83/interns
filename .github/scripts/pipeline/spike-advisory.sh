#!/usr/bin/env bash
#
# Post the spike advisory on a `type:spike` issue after estimation. The estimate
# is the end of a spike's pipeline path — no coder picks it up — so the owner
# needs that spelled out. The notice comes from the workflow, not the agent:
# type:spike is known from the issue's labels before the agent runs, so there's
# nothing for the agent to decide.
#
# No-op on any other issue type.
#
# pipeline/src/pipeline/spike_advisory.py is the only place this logic lives
# (interns#159) -- this is a thin shim that shells out to it.
#
# Usage: spike-advisory.sh
#   Env: ISSUE, GITHUB_REPOSITORY, GH_TOKEN

set -euo pipefail

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.spike_advisory "$ISSUE"
