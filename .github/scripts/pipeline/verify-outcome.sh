#!/usr/bin/env bash
#
# Backstop for an issue-pipeline phase that exited 0 without leaving the issue
# in one of its expected terminal states — the agent stopped partway. Flags the
# issue for a human and says so in a comment. A no-op when the issue already
# carries an expected label.
#
# Usage: verify-outcome.sh <phase> <issue> <expected-label>...
#   e.g. verify-outcome.sh Refinement 42 status:refined status:needs-attention

set -euo pipefail
# shellcheck source=.github/scripts/pipeline/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

phase="$1"
issue="$2"
shift 2
expected=("$@")

current=$(gh issue view "$issue" --repo "$GITHUB_REPOSITORY" --json labels --jq '[.labels[].name] | join(",")')
for label in "${expected[@]}"; do
  if [[ ",$current," == *",$label,"* ]]; then
    exit 0
  fi
done

# "`a`, `b`, or `c`" — the human-readable list for the comment.
human=""
last=$((${#expected[@]} - 1))
for i in "${!expected[@]}"; do
  if [[ "$i" -eq 0 ]]; then
    sep=""
  elif [[ "$i" -eq "$last" && "${#expected[@]}" -eq 2 ]]; then
    sep=" or "
  elif [[ "$i" -eq "$last" ]]; then
    sep=", or "
  else
    sep=", "
  fi
  human+="${sep}\`${expected[$i]}\`"
done

set_issue_status "$issue" status:needs-attention
gh issue comment "$issue" --repo "$GITHUB_REPOSITORY" --body \
  "$phase run completed without leaving the issue in $human — likely stopped partway through. See the run: $(run_url)"
