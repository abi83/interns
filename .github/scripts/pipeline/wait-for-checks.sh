#!/usr/bin/env bash
#
# Reviewer gate. The `test` and `build` checks (deploy.yml) are the single
# source of truth for "is it green" — the reviewer no longer runs them itself
# (#134). Waits for both to finish, then writes `ok` (and `reason` when not ok)
# to $GITHUB_OUTPUT. A red check routes to a human, no coder retry loop (#133).
# A manual workflow_dispatch review is an explicit override and skips the gate.
#
# Usage: wait-for-checks.sh <pr-number>
#   Env knobs (defaults match CI): CHECK_TIMEOUT_SECONDS=1200, CHECK_POLL_SECONDS=20

set -euo pipefail

PR="$1"
REPO="$GITHUB_REPOSITORY"
TIMEOUT="${CHECK_TIMEOUT_SECONDS:-1200}"
POLL="${CHECK_POLL_SECONDS:-20}"

if [[ "$GITHUB_EVENT_NAME" == "workflow_dispatch" ]]; then
  echo "Manual dispatch — skipping the check gate."
  echo "ok=true" >> "$GITHUB_OUTPUT"
  exit 0
fi

DEADLINE=$((SECONDS + TIMEOUT))
while [ "$SECONDS" -lt "$DEADLINE" ]; do
  JSON=$(gh pr checks "$PR" --repo "$REPO" --json name,bucket 2>/dev/null || echo '[]')
  TEST=$(jq -r '[.[] | select(.name=="test")] | .[0].bucket // "missing"' <<<"$JSON")
  BUILD=$(jq -r '[.[] | select(.name=="build")] | .[0].bucket // "missing"' <<<"$JSON")
  echo "test=$TEST build=$BUILD"
  if [[ "$TEST" == "fail" || "$TEST" == "cancel" || "$BUILD" == "fail" || "$BUILD" == "cancel" ]]; then
    echo "ok=false" >> "$GITHUB_OUTPUT"
    echo "reason=\`test\`=$TEST, \`build\`=$BUILD" >> "$GITHUB_OUTPUT"
    exit 0
  fi
  if [[ ( "$TEST" == "pass" || "$TEST" == "skipping" ) && ( "$BUILD" == "pass" || "$BUILD" == "skipping" ) ]]; then
    echo "ok=true" >> "$GITHUB_OUTPUT"
    exit 0
  fi
  sleep "$POLL"
done
echo "ok=false" >> "$GITHUB_OUTPUT"
echo "reason=timed out waiting for the \`test\` / \`build\` checks to complete" >> "$GITHUB_OUTPUT"
