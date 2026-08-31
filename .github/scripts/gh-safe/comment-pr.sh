#!/usr/bin/env bash
#
# Posts a comment on a PR, reading the comment body from a fixed file
# (written beforehand with the Write tool) so model-authored text never
# passes through a Bash argument. Unlike comment-issue.sh, the PR number
# isn't derivable from the triggering event here (the coder's fix-round
# run is triggered by an issue label event, not a PR event), so it's
# supplied explicitly by the workflow.
#
# Usage: write the comment text to $COMMENT_FILE, set $PR_NUMBER, then
# run with no arguments.

set -euo pipefail

COMMENT_FILE="${COMMENT_FILE:-./.pr-comment.md}"

if ! [[ "${PR_NUMBER:-}" =~ ^[0-9]+$ ]]; then
  echo "Error: PR_NUMBER not set" >&2
  exit 1
fi

if [[ ! -f "$COMMENT_FILE" ]]; then
  echo "Error: $COMMENT_FILE not found — write the comment there first" >&2
  exit 1
fi

gh pr comment "$PR_NUMBER" --body-file "$COMMENT_FILE"
