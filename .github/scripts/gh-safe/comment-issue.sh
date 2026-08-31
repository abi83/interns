#!/usr/bin/env bash
#
# Posts a comment on the issue bound to the triggering event, reading the
# comment body from a fixed file (written beforehand with the Write tool).
# Content never passes through a Bash argument — see edit-issue-body.sh
# for why.
#
# Usage: write the comment text to $COMMENT_FILE, then run with no arguments.

set -euo pipefail

COMMENT_FILE="${COMMENT_FILE:-./.issue-pipeline-comment.md}"

ISSUE=$(jq -r '.issue.number // .inputs.issue_number // empty' "${GITHUB_EVENT_PATH:?GITHUB_EVENT_PATH not set}")
if ! [[ "$ISSUE" =~ ^[0-9]+$ ]]; then
  echo "Error: no issue number in event payload" >&2
  exit 1
fi

if [[ ! -f "$COMMENT_FILE" ]]; then
  echo "Error: $COMMENT_FILE not found — write the comment there first" >&2
  exit 1
fi

gh issue comment "$ISSUE" --body-file "$COMMENT_FILE"
