#!/usr/bin/env bash
#
# Runs after a successful coder phase. If a PR now references the issue, hand it
# to the reviewer (the issue stays status:in-progress for the whole active run,
# #133 — the pr:* label is the only "which agent" signal, and a red check or
# rejection is read from native PR state, not a label). If no PR was left, the
# agent stopped for clarification or partway through — flag it for a human.
#
# pipeline/src/pipeline/handoff_to_review.py is the only place this logic
# lives (interns#159) -- this is a thin shim that shells out to it.
#
# Usage: handoff-to-review.sh <issue> <pr-number-or-empty>

set -euo pipefail

issue="$1"
pr="${2:-}"

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.handoff_to_review "$issue" "$pr"
