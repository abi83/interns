#!/usr/bin/env bash
#
# Writes a Markdown run summary to $GITHUB_STEP_SUMMARY so the Actions run page
# shows what an agent phase did without opening the turn-by-turn step log.
# Complements report-run.sh: same cost figure, but richer detail and on the run
# page only, never the ticket.
#
# Best-effort — never fails the job. Every gh lookup falls back to a plain
# line and the caller runs it with `if: always()`, so a summary lands even
# when the Claude step itself failed.
#
# Usage: run-summary.sh <phase> <execution-file> [--issue N] [--pr N]
#                       [--round initial|fix] [--cost-warn USD]
#   phase       Coder | Review | Refinement | Estimation
#   --round     Coder/Review only: whether this run is an initial pass or a fix round
#   --cost-warn append a ⚠️ line when the run cost exceeds this figure
#   execution-file may be empty/absent — a SIGKILLed (timed-out) agent step
#   leaves none; the summary then reports a timeout.
#   Env: GH_TOKEN; REVIEWER_BOT for the Review phase
#
# pipeline/src/pipeline/run_summary.py is the only place this logic lives
# (interns#159) -- this is a thin shim that shells out to it.

set -euo pipefail

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.run_summary "$@"
