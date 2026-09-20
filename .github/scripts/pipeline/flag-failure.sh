#!/usr/bin/env bash
#
# Common failure handler for the agent phases: send the issue to
# status:needs-attention, mark the PR pr:needs-attention (or just clear its
# label on a fix-round crash, which escalates issue-side), and post a comment
# linking the run.
#
# Usage: flag-failure.sh --noun <noun> [--issue N] [--pr N] [--fix-round]
#   --noun       verb for the standard comment ("Automated <noun> failed.")
#   --issue      issue to move to needs-attention / comment on
#   --pr         PR to clear labels on / comment on
#   --fix-round  coder fix-round: comment on the issue with the re-dispatch
#                command instead of the standard message
#
# pipeline/src/pipeline/flag_failure.py is the only place this logic lives
# (interns#159) -- this is a thin shim that shells out to it.

set -euo pipefail

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.flag_failure "$@"
