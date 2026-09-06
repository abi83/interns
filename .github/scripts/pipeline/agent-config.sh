#!/usr/bin/env bash
#
# Resolves the effective execution limits for one agent job and appends them
# to $GITHUB_OUTPUT (model, max_turns, timeout_minutes, max_output_tokens,
# cost_warn_usd, wiki_enabled, wiki_repo). The workflow wires those into
# --model / --max-turns / CLAUDE_CODE_MAX_OUTPUT_TOKENS / the step timeout,
# passes cost_warn_usd to run-summary.sh, and uses wiki_enabled/wiki_repo to
# decide whether to check out a wiki.
#
# Precedence per key: agents.<name>.<key> > defaults.<key> > built-in default.
# The config file is optional — with no file every key falls through to the
# built-in. There is no other override layer (no Actions variables): one
# file, one fallback.
#
# A malformed file or an unknown agent/key exits non-zero; the job's
# `Flag failure` step then posts the standard "pipeline failed" comment.
#
# Usage: agent-config.sh <refiner|estimator|coder|reviewer>
# Env:   INTERNS_CONFIG  config path (default .github/interns.yml)

set -euo pipefail

agent="${1:?usage: agent-config.sh <refiner|estimator|coder|reviewer>}"
config="${INTERNS_CONFIG:-.github/interns.yml}"

known_agents=" refiner estimator coder reviewer "
known_keys=" model max_turns timeout_minutes max_output_tokens cost_warn_usd "

# The refiner runs a codebase investigation pass before rewriting the issue
# body, so the whole pipeline defaults to claude-sonnet-5 rather than a
# cheaper model. A consumer can still drop it per phase via
# agents.refiner.model in the config file.
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

wiki_enabled=false
wiki_repo=""

if [[ -f "$config" ]]; then
  yq -e 'type == "!!map"' "$config" >/dev/null 2>&1 || die "$config is not valid YAML or not a mapping"

  while IFS= read -r k; do
    [[ -z "$k" ]] && continue
    case "$k" in
      # `checks` (the reviewer's ignore list) is consumed by wait-for-checks.sh,
      # not here — accept it so a valid config doesn't trip the unknown-key gate.
      defaults | agents | wiki | checks) ;;
      *) die "unknown top-level key '$k' in $config" ;;
    esac
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

  while IFS= read -r k; do
    [[ -z "$k" ]] && continue
    case "$k" in
      enabled | url) ;;
      *) die "unknown key 'wiki.$k' in $config" ;;
    esac
  done < <(yq '.wiki // {} | keys | .[]' "$config")

  for k in model max_turns timeout_minutes max_output_tokens cost_warn_usd; do
    v=$(yq ".agents.$agent.$k // .defaults.$k // \"\"" "$config")
    [[ -n "$v" && "$v" != "null" ]] && printf -v "file_$k" '%s' "$v"
  done

  if [[ "$(yq '.wiki.enabled // false' "$config")" == "true" ]]; then
    wiki_enabled=true
    wiki_repo=$(yq '.wiki.url // ""' "$config")
    [[ -n "$wiki_repo" ]] || die "wiki.enabled is true but wiki.url is unset in $config"
  fi
fi

resolve() {
  local key="$1" fvar
  fvar="file_$key"
  if [[ -n "${!fvar:-}" ]]; then printf '%s' "${!fvar}"; return; fi
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
  echo "wiki_enabled=$wiki_enabled"
  echo "wiki_repo=$wiki_repo"
} >> "${GITHUB_OUTPUT:-/dev/stdout}"

echo "agent-config[$agent]: model=$model max_turns=$max_turns timeout_minutes=$timeout_minutes max_output_tokens=$max_output_tokens cost_warn_usd=$cost_warn_usd wiki_enabled=$wiki_enabled" >&2
