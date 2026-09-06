#!/usr/bin/env bash
#
# Reviewer gate. Waits for every check on the PR to finish, then writes `ok`
# (and `reason` when not ok) to $GITHUB_OUTPUT:
#
#   - any check red (fail / cancel)              -> ok=false, route to a human (#133)
#   - every check green (pass, or skipping)      -> ok=true, the reviewer runs
#   - anything still pending                     -> keep polling to the timeout,
#                                                   then ok=false ("timed out")
#
# The reviewer's own run is excluded from the set it waits on (its checks carry
# this run's id in their link), otherwise it would wait on itself forever.
# Checks named in `checks.ignore` in .github/interns.yml are excluded too, for
# repos that run non-blocking advisory checks (preview deploys, coverage deltas).
#
# A manual workflow_dispatch review is an explicit override and skips the gate.
#
# Usage: wait-for-checks.sh <pr-number>
#   Env knobs (defaults match CI): CHECK_TIMEOUT_SECONDS=1200,
#   CHECK_POLL_SECONDS=20, CHECK_SETTLE_SECONDS=30 (grace for checks to register
#   on a PR that reports none yet).

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

# Reduce the PR's checks to the ones this gate cares about (not our own run,
# not explicitly ignored) and classify them: `.red` is "name=bucket" for every
# failed/cancelled check, `.pending` is the names still running, `.total` is
# how many checks were considered.
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
