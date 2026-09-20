#!/usr/bin/env bash
#
# Posts the "<Phase> [pipeline run](url) — cost: $X" comment every agent phase
# drops on the ticket. Cost tracking lives on the issue (refine, estimate,
# coder and reviewer all post there) so spend aggregates from one place — see
# #105. Cost is parsed from the claude-code-action execution file; "unknown"
# when the run produced none.
#
# Usage: report-run.sh <phase> <execution-file> <issue-number> [<pr-number>] [--warn TEXT]
#   Comments on the issue. Falls back to the PR only when issue-number is
#   empty — the reviewer on a PR with no linked issue.
#   --warn appends a "⚠️ TEXT" line to the same comment, e.g. a nudge that
#   tests/build aren't configured for this repo.
#
# pipeline/src/pipeline/report_run.py is the only place this logic lives
# (interns#159) -- this is a thin shim that shells out to it.

set -euo pipefail

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.report_run "$@"
