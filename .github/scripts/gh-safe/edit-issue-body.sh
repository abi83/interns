#!/usr/bin/env bash
#
# Sets the body of the issue bound to the triggering event, reading the
# new body from a fixed file (written beforehand with the Write tool).
# Content never passes through a Bash argument, since multi-line markdown
# containing "#" headers trips Claude Code's static shell-safety checks
# when quoted as a CLI arg.
#
# Usage: write the new body to $BODY_FILE, then run with no arguments.

set -euo pipefail

BODY_FILE="${BODY_FILE:-./.issue-pipeline-body.md}"

ISSUE=$(jq -r '.issue.number // .inputs.issue_number // empty' "${GITHUB_EVENT_PATH:?GITHUB_EVENT_PATH not set}")
if ! [[ "$ISSUE" =~ ^[0-9]+$ ]]; then
  echo "Error: no issue number in event payload" >&2
  exit 1
fi

if [[ ! -f "$BODY_FILE" ]]; then
  echo "Error: $BODY_FILE not found — write the new body there first" >&2
  exit 1
fi

gh issue edit "$ISSUE" --body-file "$BODY_FILE"
