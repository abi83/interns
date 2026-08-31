#!/usr/bin/env bash
#
# Runs after a successful coder phase. If a PR now references the issue, hand it
# to the reviewer (the issue stays status:in-progress for the whole active run,
# #133 — the pr:* label is the only "which agent" signal, and a red check or
# rejection is read from native PR state, not a label). If no PR was left, the
# agent stopped for clarification or partway through — flag it for a human.
#
# Usage: handoff-to-review.sh <issue> <pr-number-or-empty>

set -euo pipefail
# shellcheck source=.github/scripts/pipeline/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

issue="$1"
pr="${2:-}"

if [[ -n "$pr" ]]; then
  set_pr_pipeline_label "$pr" pr:in-review
else
  set_issue_status "$issue" status:needs-attention
  gh issue comment "$issue" --repo "$GITHUB_REPOSITORY" --body \
    "Coder run completed without leaving an open PR referencing this issue — likely stopped for clarification or partway through. See the run: $(run_url)"
fi
