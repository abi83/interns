#!/usr/bin/env bash
#
# Runs when a coder/reviewer PR closes. Nothing else in the pipeline reacts to a
# close, so without this the linked issue keeps status:in-progress forever: on a
# merge GitHub's `Closes #N` shuts the issue but leaves the label, and an
# unmerged close leaves the issue open with no agent owning it.
#
#   merged        -> drop status:in-progress from the (already closed) issue
#   closed, unmerged -> move the issue status:in-progress -> status:needs-attention
#                       and comment that a human needs to decide what happens next
#
# Either way, clear any stale pr:* label from the PR.
#
# Usage: handle-pr-closed.sh <pr> <issue-or-empty> <merged:true|false>
#   Env: GH_TOKEN

set -euo pipefail
# shellcheck source=.github/scripts/pipeline/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

pr="$1"
issue="${2:-}"
merged="${3:-false}"

set_pr_pipeline_label "$pr"

if [[ -z "$issue" ]]; then
  echo "PR #$pr has no linked issue — only cleared its pr:* label."
  exit 0
fi

if [[ "$merged" == "true" ]]; then
  # The issue is already closed by `Closes #N`; just retire the run label.
  current=$(gh issue view "$issue" --repo "$GITHUB_REPOSITORY" --json labels --jq '[.labels[].name] | join(",")')
  if [[ ",$current," == *",status:in-progress,"* ]]; then
    gh issue edit "$issue" --repo "$GITHUB_REPOSITORY" --remove-label status:in-progress || true
  fi
else
  set_issue_status "$issue" status:needs-attention
  gh issue comment "$issue" --repo "$GITHUB_REPOSITORY" --body \
    "[PR #$pr]($GITHUB_SERVER_URL/$GITHUB_REPOSITORY/pull/$pr) was closed without merging — this issue needs a human to decide whether to re-dispatch the coder (re-apply \`status:ready\`) or drop it. Run: $(run_url)"
fi
