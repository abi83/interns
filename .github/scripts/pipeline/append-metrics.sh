#!/usr/bin/env bash
#
# Append one or more pipeline-metrics records (see extract-metrics.sh) to
# metrics.jsonl on the orphan `metrics` branch, as a single commit per workflow
# run (#12). The caller serialises appends across runs with
# `concurrency: { group: metrics-append }`; this script additionally survives a
# concurrent human push to the branch with a fetch + re-apply + push retry loop.
# Distinct JSONL lines never actually conflict, so "rebase" here is just:
# discard our local commit, re-fetch the branch tip, re-append, re-push.
#
# The branch is created (orphan, one empty metrics.jsonl) on first use, so a
# fresh consumer repo needs no manual seeding.
#
# Usage: append-metrics.sh <record-file>...
#   Each <record-file> holds exactly one JSON object (the record).
#
# Env: GH_TOKEN (contents:write), GITHUB_REPOSITORY, GITHUB_SERVER_URL,
#      GITHUB_RUN_ID.

set -euo pipefail

BRANCH=metrics
FILE=metrics.jsonl
RETRIES=3

die() { echo "append-metrics: $*" >&2; exit 1; }

[[ $# -gt 0 ]] || die "no record files given"
: "${GH_TOKEN:?append-metrics: GH_TOKEN unset}"
: "${GITHUB_REPOSITORY:?append-metrics: GITHUB_REPOSITORY unset}"

# Validate and normalise every incoming record before touching the remote —
# one bad file aborts the whole append, nothing half-written is pushed.
records=$(mktemp)
work=$(mktemp -d)
trap 'rm -f "$records"; rm -rf "$work"' EXIT

for f in "$@"; do
  [[ -f "$f" ]] || die "no such file: $f"
  jq -e 'type == "object"' "$f" >/dev/null 2>&1 || die "not a JSON object: $f"
  jq -c . "$f" >> "$records"
done
[[ -s "$records" ]] || { echo "append-metrics: nothing to append"; exit 0; }

server="${GITHUB_SERVER_URL:-https://github.com}"
auth_remote="https://x-access-token:${GH_TOKEN}@${server#https://}/${GITHUB_REPOSITORY}.git"

push_attempt() {
  rm -rf "$work"
  mkdir -p "$work"
  git -C "$work" init -q
  git -C "$work" config user.name  "github-actions[bot]"
  git -C "$work" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
  git -C "$work" config commit.gpgsign false
  git -C "$work" remote add origin "$auth_remote"

  if git -C "$work" fetch -q --depth=1 origin "$BRANCH" 2>/dev/null; then
    git -C "$work" checkout -q -b "$BRANCH" FETCH_HEAD || return 1
  else
    git -C "$work" checkout -q --orphan "$BRANCH" || return 1
    : > "$work/$FILE"
  fi

  cat "$records" >> "$work/$FILE"
  git -C "$work" add "$FILE" || return 1
  git -C "$work" commit -q -m "chore(metrics): append records from run ${GITHUB_RUN_ID:-unknown}" || return 1
  git -C "$work" push -q origin "HEAD:$BRANCH"
}

for attempt in $(seq 1 "$RETRIES"); do
  if push_attempt; then
    echo "append-metrics: appended $(wc -l < "$records" | tr -d ' ') record(s) to $BRANCH"
    exit 0
  fi
  echo "append-metrics: attempt $attempt/$RETRIES failed" >&2
  sleep $(( attempt * 3 ))
done

die "push to $BRANCH failed after $RETRIES attempts"
