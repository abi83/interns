#!/usr/bin/env bash
#
# Hard ceiling on automatic reviewer runs for one PR, independent of the
# coder<->reviewer fix-loop cap in apply-verdict.sh. After the fix loop
# escalates, every further push still spawns a full LLM reviewer run; without a
# ceiling that is unbounded spend on a PR that takes many commits to land.
#
# Counts the reviewer bot's own prior reviews on the PR. At or over
# MAX_AUTOMATIC_REVIEWS_PER_PR it writes capped=true (the workflow then skips the
# Claude reviewer step), posts a one-line notice, and marks the PR
# pr:needs-attention so it stays discoverable. Otherwise capped=false.
#
# workflow_dispatch is an explicit human override and never calls this script.
#
# Usage: check-review-cap.sh <pr>
#   Env: REVIEWER_BOT, MAX_AUTOMATIC_REVIEWS_PER_PR, GH_TOKEN

set -euo pipefail
# shellcheck source=.github/scripts/pipeline/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

pr="$1"
repo="$GITHUB_REPOSITORY"
max="${MAX_AUTOMATIC_REVIEWS_PER_PR:-5}"

count=$(gh api "repos/$repo/pulls/$pr/reviews" \
  --jq '[.[] | select(.user.login==env.REVIEWER_BOT)] | length')

if [[ "$count" -ge "$max" ]]; then
  echo "capped=true" >> "$GITHUB_OUTPUT"
  escalate_pr "$pr"
  gh pr comment "$pr" --repo "$repo" --body \
    "Automatic review limit ($max) reached — further review is manual. Run: $(run_url)"
else
  echo "capped=false" >> "$GITHUB_OUTPUT"
fi
