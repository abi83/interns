#!/usr/bin/env bash
#
# Submits a formal PR review (verdict + optional inline comments) in one
# atomic call, reading the review from a fixed JSON file (written
# beforehand with the Write tool) so model-authored text never passes
# through a Bash argument.
#
# Expected JSON shape in $REVIEW_FILE:
#   {
#     "event": "APPROVE" | "REQUEST_CHANGES",
#     "body": "...",
#     "comments": [{"path": "...", "line": 123, "body": "..."}, ...]
#   }
#
# Usage: write the review JSON to $REVIEW_FILE, then run with no arguments.

set -euo pipefail

REVIEW_FILE="${REVIEW_FILE:-./.pr-review.json}"

PR=$(jq -r '.pull_request.number // .inputs.pr_number // empty' "${GITHUB_EVENT_PATH:?GITHUB_EVENT_PATH not set}")
if ! [[ "$PR" =~ ^[0-9]+$ ]]; then
  echo "Error: no PR number in event payload" >&2
  exit 1
fi

if [[ ! -f "$REVIEW_FILE" ]]; then
  echo "Error: $REVIEW_FILE not found — write the review JSON there first" >&2
  exit 1
fi

EVENT=$(jq -r '.event // empty' "$REVIEW_FILE")
if [[ "$EVENT" != "APPROVE" && "$EVENT" != "REQUEST_CHANGES" ]]; then
  echo "Error: review JSON's \"event\" must be APPROVE or REQUEST_CHANGES" >&2
  exit 1
fi

gh api --method POST "repos/${GITHUB_REPOSITORY}/pulls/${PR}/reviews" --input "$REVIEW_FILE"
