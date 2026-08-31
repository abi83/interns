#!/usr/bin/env bash
#
# Opens a PR from the current branch against the repo's default branch,
# reading title/body from fixed files (written beforehand with the Write
# tool) so model-authored text never passes through a Bash argument.
#
# Deterministically appends "Closes #<issue>" to the body — this is what
# lets later workflow steps resolve the linked issue from the PR via
# GitHub's own closingIssuesReferences, without trusting the model to
# reproduce that exact line every time.
#
# Usage: write the PR title to $TITLE_FILE and body to $BODY_FILE, push
# the current branch, then run with no arguments.

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
