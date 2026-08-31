#!/usr/bin/env bash
#
# Resolves the effective execution limits for one agent job and appends them to
# $GITHUB_OUTPUT (model, max_turns, timeout_minutes, max_output_tokens,
# cost_warn_usd). The workflow wires those into --model / --max-turns /
# CLAUDE_CODE_MAX_OUTPUT_TOKENS / the step timeout, and passes cost_warn_usd to
# run-summary.sh.
#
# Precedence per key: agents.<name>.<key>  >  defaults.<key>  >  Actions var
# PIPELINE_<KEY>  >  built-in default. The config file is optional — with no
# file every key falls through to the Actions var or the built-in.
#
# A malformed file or an unknown agent/key exits non-zero; the job's
# `Flag failure` step then posts the standard "pipeline failed" comment.
#
# Usage: agent-config.sh <refiner|estimator|coder|reviewer>
# Env:   AGENT_PIPELINE_CONFIG  config path (default .github/agent-pipeline.yml)

set -euo pipefail

agent="${1:?usage: agent-config.sh <refiner|estimator|coder|reviewer>}"
config="${AGENT_PIPELINE_CONFIG:-.github/agent-pipeline.yml}"

known_agents=" refiner estimator coder reviewer "
known_keys=" model max_turns timeout_minutes max_output_tokens cost_warn_usd "

builtin_default() {
  case "$1" in
    model)             echo "claude-sonnet-5" ;;
    max_turns)         echo "40" ;;
    timeout_minutes)   echo "30" ;;
    max_output_tokens) echo "32000" ;;
    cost_warn_usd)     echo "1.50" ;;
  esac
}

die() { echo "agent-config: $*" >&2; exit 1; }

[[ "$known_agents" == *" $agent "* ]] || die "unknown agent '$agent'"

if [[ -f "$config" ]]; then
  yq -e 'type == "!!map"' "$config" >/dev/null 2>&1 || die "$config is not valid YAML or not a mapping"

  while IFS= read -r k; do
    [[ -z "$k" ]] && continue
    [[ "$k" == "defaults" || "$k" == "agents" ]] || die "unknown top-level key '$k' in $config"
  done < <(yq 'keys | .[]' "$config")

  while IFS= read -r k; do
    [[ -z "$k" ]] && continue
    [[ "$known_keys" == *" $k "* ]] || die "unknown key 'defaults.$k' in $config"
  done < <(yq '.defaults // {} | keys | .[]' "$config")

  while IFS= read -r a; do
    [[ -z "$a" ]] && continue
    [[ "$known_agents" == *" $a "* ]] || die "unknown agent '$a' in $config"
    while IFS= read -r k; do
      [[ -z "$k" ]] && continue
      [[ "$known_keys" == *" $k "* ]] || die "unknown key 'agents.$a.$k' in $config"
    done < <(yq ".agents.$a // {} | keys | .[]" "$config")
  done < <(yq '.agents // {} | keys | .[]' "$config")

  for k in model max_turns timeout_minutes max_output_tokens cost_warn_usd; do
    v=$(yq ".agents.$agent.$k // .defaults.$k // \"\"" "$config")
    [[ -n "$v" && "$v" != "null" ]] && printf -v "file_$k" '%s' "$v"
  done
fi

resolve() {
  local key="$1" fvar evar
  fvar="file_$key"
  if [[ -n "${!fvar:-}" ]]; then printf '%s' "${!fvar}"; return; fi
  evar="PIPELINE_$(printf '%s' "$key" | tr '[:lower:]' '[:upper:]')"
  if [[ -n "${!evar:-}" ]]; then printf '%s' "${!evar}"; return; fi
  builtin_default "$key"
}

model=$(resolve model)
max_turns=$(resolve max_turns)
timeout_minutes=$(resolve timeout_minutes)
max_output_tokens=$(resolve max_output_tokens)
cost_warn_usd=$(resolve cost_warn_usd)

is_int_ge() { [[ "$1" =~ ^[0-9]+$ ]] && [[ "$1" -ge "$2" ]]; }
is_num_gt0() { awk -v x="$1" 'BEGIN { exit !(x + 0 > 0) }'; }

[[ -n "$model" ]] || die "model resolved empty"
is_int_ge "$max_turns" 1 || die "max_turns must be a positive integer (got '$max_turns')"
is_int_ge "$timeout_minutes" 1 || die "timeout_minutes must be a positive integer (got '$timeout_minutes')"
is_int_ge "$max_output_tokens" 16000 \
  || die "max_output_tokens must be an integer >= 16000 (got '$max_output_tokens') — it is a safety ceiling, not a cost lever"
is_num_gt0 "$cost_warn_usd" || die "cost_warn_usd must be a positive number (got '$cost_warn_usd')"

{
  echo "model=$model"
  echo "max_turns=$max_turns"
  echo "timeout_minutes=$timeout_minutes"
  echo "max_output_tokens=$max_output_tokens"
  echo "cost_warn_usd=$cost_warn_usd"
} >> "${GITHUB_OUTPUT:-/dev/stdout}"

echo "agent-config[$agent]: model=$model max_turns=$max_turns timeout_minutes=$timeout_minutes max_output_tokens=$max_output_tokens cost_warn_usd=$cost_warn_usd" >&2
