#!/usr/bin/env bash
#
# Reviewer gate: block until every check on the PR has finished, then write
# `ok` (and `reason` when not ok) to $GITHUB_OUTPUT. A red check routes the PR
# to a human with no coder retry (#133); workflow_dispatch skips the gate.
#
# Two things are excluded from the wait: this workflow run's own checks (they
# never finish before the gate does) and anything in `checks.ignore` in
# .github/interns.yml (non-blocking advisory checks).
#
# Usage: wait-for-checks.sh <pr-number>
#   Env: CHECK_TIMEOUT_SECONDS=1200, CHECK_POLL_SECONDS=20, CHECK_SETTLE_SECONDS=30

set -euo pipefail

PR="$1"
REPO="$GITHUB_REPOSITORY"
TIMEOUT="${CHECK_TIMEOUT_SECONDS:-1200}"
POLL="${CHECK_POLL_SECONDS:-20}"
SETTLE="${CHECK_SETTLE_SECONDS:-30}"
RUN_ID="${GITHUB_RUN_ID:-}"
CONFIG="${INTERNS_CONFIG:-.github/interns.yml}"

emit() { echo "$1" >> "$GITHUB_OUTPUT"; }

if [[ "${GITHUB_EVENT_NAME:-}" == "workflow_dispatch" ]]; then
  echo "Manual dispatch — skipping the check gate."
  emit "ok=true"
  exit 0
fi

IGNORE='[]'
if [[ -f "$CONFIG" ]]; then
  IGNORE=$(yq -o=json -I=0 '.checks.ignore // []' "$CONFIG" 2>/dev/null || echo '[]')
  jq -e 'type == "array"' <<<"$IGNORE" >/dev/null 2>&1 || IGNORE='[]'
fi

# checks JSON -> {total, red: ["name=bucket"...], pending: ["name"...]},
# dropping this run's own checks and any ignored by name.
classify() {
  jq -c --arg run "$RUN_ID" --argjson ignore "$IGNORE" '
    [ .[]
      | select($run == "" or ((.link // "") | contains("/runs/" + $run + "/") | not))
      | select(.name as $n | ($ignore | index($n)) | not)
    ] as $c
    | { total:   ($c | length),
        red:     [ $c[] | select(.bucket == "fail" or .bucket == "cancel") | "\(.name)=\(.bucket)" ],
        pending: [ $c[] | select(.bucket == "pending") | .name ] }'
}

DEADLINE=$((SECONDS + TIMEOUT))
last_pending='[]'
while :; do
  raw=$(gh pr checks "$PR" --repo "$REPO" --json name,bucket,link 2>/dev/null || true)
  jq -e 'type == "array"' <<<"$raw" >/dev/null 2>&1 || raw='[]'
  summary=$(classify <<<"$raw")

  total=$(jq -r '.total' <<<"$summary")
  red=$(jq -r '.red | join(", ")' <<<"$summary")
  pending_n=$(jq -r '.pending | length' <<<"$summary")
  last_pending=$(jq -c '.pending' <<<"$summary")
  echo "checks: total=$total red=[$red] pending=$pending_n"

  if [[ -n "$red" ]]; then
    emit "ok=false"
    emit "reason=red checks: $red"
    exit 0
  fi
  # No checks yet: wait out the settle window in case CI is still registering.
  if [[ "$total" -eq 0 && "$SECONDS" -ge "$SETTLE" ]]; then
    echo "No checks reported on this PR — nothing to wait on."
    emit "ok=true"
    exit 0
  fi
  if [[ "$total" -gt 0 && "$pending_n" -eq 0 ]]; then
    emit "ok=true"
    exit 0
  fi
  [ "$SECONDS" -ge "$DEADLINE" ] && break
  sleep "$POLL"
done

names=$(jq -r 'join(", ")' <<<"$last_pending")
emit "ok=false"
emit "reason=timed out waiting for checks to finish: ${names:-unknown}"
