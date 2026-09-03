#!/usr/bin/env bash
#
# Parse one claude-code-action execution file into a single pipeline-metrics
# record (one JSON object) on stdout, for append-metrics.sh to persist.
#
# Usage: extract-metrics.sh <execution-file> --job <job> [--issue N] [--pr N]
#
# Bump SCHEMA_VERSION and .github/pipeline-metrics.schema.json together on any
# breaking shape change. Exits non-zero, printing nothing, when the file is
# missing or has no result event (a killed run can leave a truncated file).

set -euo pipefail

SCHEMA_VERSION=1

die() { echo "extract-metrics: $*" >&2; exit 1; }

exec_file="${1:-}"
[[ -n "$exec_file" ]] || die "missing execution-file argument"
shift

job="" issue="" pr=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --job)   job="${2:-}"; shift 2 ;;
    --issue) issue="${2:-}"; shift 2 ;;
    --pr)    pr="${2:-}"; shift 2 ;;
    *) die "unknown argument: $1" ;;
  esac
done

case "$job" in
  refiner|estimator|coder|reviewer) ;;
  *) die "--job must be one of refiner|estimator|coder|reviewer (got '$job')" ;;
esac
[[ -f "$exec_file" ]] || die "execution file not found: $exec_file"
jq -e '[.[] | select(.type=="result")] | length > 0' "$exec_file" >/dev/null 2>&1 \
  || die "no result event in $exec_file"

num_or_null() { [[ "${1:-}" =~ ^[0-9]+$ ]] && echo "$1" || echo "null"; }

timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

jq -c -n \
  --slurpfile events "$exec_file" \
  --argjson schema_version "$SCHEMA_VERSION" \
  --arg timestamp "$timestamp" \
  --arg repo "${GITHUB_REPOSITORY:?extract-metrics: GITHUB_REPOSITORY unset}" \
  --argjson run_id "${GITHUB_RUN_ID:?extract-metrics: GITHUB_RUN_ID unset}" \
  --argjson run_attempt "${GITHUB_RUN_ATTEMPT:-1}" \
  --arg job "$job" \
  --argjson issue "$(num_or_null "$issue")" \
  --argjson pr "$(num_or_null "$pr")" \
  '
  ($events[0]) as $ev
  | ([$ev[] | select(.type=="result")] | last) as $r
  | ([$ev[]
       | select(.type=="assistant" and (.isSidechain != true))
       | .message.content[]? | select(.type=="tool_use") | .name]
     | reduce .[] as $n ({}; .[$n] += 1)) as $tool_calls
  | {
      schema_version: $schema_version,
      timestamp: $timestamp,
      repo: $repo,
      run_id: $run_id,
      run_attempt: $run_attempt,
      job: $job,
      issue: $issue,
      pr: $pr,
      session_id: ($r.session_id // null),
      agent_result: ($r.subtype // null),
      num_turns: ($r.num_turns // null),
      duration_ms: ($r.duration_ms // null),
      duration_api_ms: ($r.duration_api_ms // null),
      models: (
        ($r.modelUsage // {})
        | to_entries
        | map({
            key: .key,
            value: {
              input_tokens:          (.value.inputTokens // 0),
              output_tokens:         (.value.outputTokens // 0),
              cache_read_tokens:     (.value.cacheReadInputTokens // 0),
              cache_creation_tokens: (.value.cacheCreationInputTokens // 0),
              cost_usd:              (.value.costUSD // 0)
            }
          })
        | from_entries
      ),
      tool_calls: $tool_calls
    }
  '
