#!/usr/bin/env bash
#
# Comments on a PR, reading the body from a fixed file so model-authored
# text never passes through a Bash argument. $PR_NUMBER is explicit: the
# fix-round run is triggered by an issue label event, not a PR event.
#
# Usage: write the text to $COMMENT_FILE, set $PR_NUMBER, run with no args.

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
