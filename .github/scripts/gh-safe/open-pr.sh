#!/usr/bin/env bash
#
# Opens a PR from the current branch, reading title/body from fixed files
# so model-authored text never passes through a Bash argument.
#
# Appends "Closes #<issue>" deterministically, so later workflow steps can
# resolve the linked issue via GitHub's closingIssuesReferences rather than
# trusting the model to reproduce that line.
#
# Usage: write $TITLE_FILE and $BODY_FILE, push the branch, run with no args.

set -euo pipefail

TITLE_FILE="${TITLE_FILE:-./.pr-title.txt}"
BODY_FILE="${BODY_FILE:-./.pr-body.md}"

ISSUE=$(jq -r '.issue.number // .inputs.issue_number // empty' "${GITHUB_EVENT_PATH:?GITHUB_EVENT_PATH not set}")
if ! [[ "$ISSUE" =~ ^[0-9]+$ ]]; then
  echo "Error: no issue number in event payload" >&2
  exit 1
fi

if [[ ! -f "$TITLE_FILE" ]]; then
  echo "Error: $TITLE_FILE not found — write the PR title there first" >&2
  exit 1
fi
if [[ ! -f "$BODY_FILE" ]]; then
  echo "Error: $BODY_FILE not found — write the PR body there first" >&2
  exit 1
fi

FULL_BODY_FILE=$(mktemp)
cat "$BODY_FILE" > "$FULL_BODY_FILE"
printf '\n\nCloses #%s\n' "$ISSUE" >> "$FULL_BODY_FILE"

gh pr create \
  --title "$(cat "$TITLE_FILE")" \
  --body-file "$FULL_BODY_FILE"
