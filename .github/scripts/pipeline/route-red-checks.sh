#!/usr/bin/env bash
#
# The `test` / `build` checks aren't green, so the reviewer won't run. The
# coder writes and runs tests before pushing, so a red check here goes straight
# to a human rather than back through a coder retry (#133).
#
# Usage: route-red-checks.sh <pr> <issue-or-empty> <reason>

set -euo pipefail
# shellcheck source=.github/scripts/pipeline/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

pr="$1"
issue="${2:-}"
reason="$3"

set_pr_pipeline_label "$pr"
gh pr comment "$pr" --repo "$GITHUB_REPOSITORY" --body \
  "Required checks are not green ($reason) — the reviewer won't run. The coder writes and runs tests before pushing, so this is being sent straight to a human rather than retried. Run: $(run_url)"
if [[ -n "$issue" ]]; then
  set_issue_status "$issue" status:needs-attention
fi
