#!/usr/bin/env bash
#
# Checks out a PR's branch and writes the latest review round to $GITHUB_OUTPUT
# as `text` for the coder fix-round prompt: the most recent CHANGES_REQUESTED
# review, its line-anchored comments, and any conversation posted after it.
# Earlier rounds are already addressed in prior commits — feeding them back in
# makes the coder re-litigate resolved points (contradicts code-fix.md).
#
# Usage: gather-fix-feedback.sh <pr-number> <head-ref> <issue-number>

set -euo pipefail

PR="$1"
HEAD_REF="$2"
ISSUE="$3"
REPO="$GITHUB_REPOSITORY"

if [[ -z "$PR" ]]; then
  echo "Error: fix round dispatched but no open PR references issue #$ISSUE" >&2
  exit 1
fi

git fetch origin "$HEAD_REF"
git checkout "$HEAD_REF"

LATEST_REVIEW=$(gh api "repos/$REPO/pulls/$PR/reviews" --paginate \
  --jq '[.[] | select(.state=="CHANGES_REQUESTED")] | last')
if [[ -z "$LATEST_REVIEW" || "$LATEST_REVIEW" == "null" ]]; then
  echo "Error: fix round for PR #$PR but no CHANGES_REQUESTED review found" >&2
  exit 1
fi
REVIEW_ID=$(jq -r '.id' <<<"$LATEST_REVIEW")
REVIEW_TS=$(jq -r '.submitted_at' <<<"$LATEST_REVIEW")
export REVIEW_ID REVIEW_TS

{
  echo 'text<<EOF_FEEDBACK'
  echo "## Latest REQUEST_CHANGES review — $REVIEW_TS"
  echo
  jq -r '.body // "(no summary body)"' <<<"$LATEST_REVIEW"
  echo
  echo "## Inline comments on that review"
  gh api "repos/$REPO/pulls/$PR/comments" --paginate \
    --jq '[.[] | select((.pull_request_review_id | tostring) == env.REVIEW_ID)]
          | sort_by(.created_at)
          | .[] | "- \(.path):\(.line // .original_line // "?")\n  \(.body)"'
  echo
  echo "## PR conversation posted after that review"
  gh api "repos/$REPO/issues/$PR/comments" --paginate \
    --jq '[.[] | select(.created_at > env.REVIEW_TS)]
          | sort_by(.created_at)
          | .[] | "### \(.user.login) (\(.created_at))\n\(.body)"'
  echo 'EOF_FEEDBACK'
} >> "$GITHUB_OUTPUT"
