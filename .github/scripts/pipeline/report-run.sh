#!/usr/bin/env bash
#
# Posts the "<Phase> [pipeline run](url) — cost: $X" comment every agent phase
# drops on the ticket. Cost tracking lives on the issue (refine, estimate,
# coder and reviewer all post there) so spend aggregates from one place — see
# #105. Cost is parsed from the claude-code-action execution file; "unknown"
# when the run produced none.
#
# Usage: report-run.sh <phase> <execution-file> <issue-number> [<pr-number>]
#   Comments on the issue. Falls back to the PR only when issue-number is
#   empty — the reviewer on a PR with no linked issue.

set -euo pipefail
# shellcheck source=.github/scripts/pipeline/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

phase="$1"
exec_file="$2"
issue="${3:-}"
pr="${4:-}"

raw_cost=$(jq -r '[.[] | select(.type=="result")][0].total_cost_usd // empty' "$exec_file" 2>/dev/null || true)
body="$phase [pipeline run]($(run_url)) — cost: \$$(format_cost "$raw_cost")"

if [[ -n "$issue" ]]; then
  gh issue comment "$issue" --repo "$GITHUB_REPOSITORY" --body "$body"
elif [[ -n "$pr" ]]; then
  gh pr comment "$pr" --repo "$GITHUB_REPOSITORY" --body "$body"
else
  echo "report-run: need an issue or PR number" >&2
  exit 1
fi
