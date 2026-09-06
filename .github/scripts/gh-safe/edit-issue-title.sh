#!/usr/bin/env bash
#
# Sets the title of the issue bound to the triggering event, reading the
# new title from a fixed file (written beforehand with the Write tool).
# Content never passes through a Bash argument, matching edit-issue-body.sh
# and keeping titles with shell metacharacters out of the command line.
#
# Usage: write the new title to $TITLE_FILE, then run with no arguments.

set -euo pipefail

TITLE_FILE="${TITLE_FILE:-./.issue-pipeline-title.md}"

ISSUE=$(jq -r '.issue.number // .inputs.issue_number // empty' "${GITHUB_EVENT_PATH:?GITHUB_EVENT_PATH not set}")
if ! [[ "$ISSUE" =~ ^[0-9]+$ ]]; then
  echo "Error: no issue number in event payload" >&2
  exit 1
fi

if [[ ! -f "$TITLE_FILE" ]]; then
  echo "Error: $TITLE_FILE not found — write the new title there first" >&2
  exit 1
fi

# A title is a single line; collapse any trailing newline and reject a
# multi-line file rather than silently sending only the first line.
if [[ $(grep -c '' "$TITLE_FILE") -gt 1 ]]; then
  echo "Error: $TITLE_FILE has more than one line — a title is a single line" >&2
  exit 1
fi

TITLE=$(head -n 1 "$TITLE_FILE")
if [[ -z "$TITLE" ]]; then
  echo "Error: $TITLE_FILE is empty" >&2
  exit 1
fi

gh issue edit "$ISSUE" --title "$TITLE"
