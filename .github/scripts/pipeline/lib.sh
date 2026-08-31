#!/usr/bin/env bash
#
# Shared helpers for the pipeline scripts. Source it, don't execute:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
#
# Every helper reads the Actions env the workflow already exports:
# GITHUB_REPOSITORY, GITHUB_SERVER_URL, GITHUB_RUN_ID, GH_TOKEN.

set -euo pipefail

# URL of the current workflow run, for "see the run" links in comments.
run_url() {
  echo "${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
}

# Raw USD cost from a claude-code-action execution file -> 4dp, or "unknown"
# when the run produced no cost figure.
format_cost() {
  local raw="${1:-}"
  if [[ -n "$raw" ]]; then
    printf '%.4f' "$raw"
  else
    printf 'unknown'
  fi
}

# Issue lifecycle labels the coder/reviewer phases move between. The
# issue-pipeline's own labels (needs-refinement, refined, estimated) are left
# untouched here.
_ISSUE_STATUS_LABELS=(status:in-progress status:needs-attention status:ready)

# Move an issue to one lifecycle status, removing whichever of the others it
# currently carries (a --remove-label for an absent label would fail the whole
# edit). Best-effort: a failed edit doesn't abort the caller.
set_issue_status() {
  local issue="$1" target="$2" current label
  local args=(issue edit "$issue" --repo "$GITHUB_REPOSITORY" --add-label "$target")
  current=$(gh issue view "$issue" --repo "$GITHUB_REPOSITORY" --json labels --jq '[.labels[].name] | join(",")')
  for label in "${_ISSUE_STATUS_LABELS[@]}"; do
    [[ "$label" == "$target" ]] && continue
    [[ ",$current," == *",$label,"* ]] && args+=(--remove-label "$label")
  done
  gh "${args[@]}" || true
  return 0
}

# The PR label marking which agent is on it now.
_PR_PIPELINE_LABELS=(pr:coding pr:in-review)

# Set the PR's pipeline label, or clear both when called with no label (the
# reviewer is done and no agent is active). Only touches labels that change.
set_pr_pipeline_label() {
  local pr="$1" target="${2:-}" current label
  local base=(pr edit "$pr" --repo "$GITHUB_REPOSITORY")
  local args=("${base[@]}")
  current=$(gh pr view "$pr" --repo "$GITHUB_REPOSITORY" --json labels --jq '[.labels[].name] | join(",")')
  for label in "${_PR_PIPELINE_LABELS[@]}"; do
    if [[ "$label" == "$target" ]]; then
      [[ ",$current," == *",$label,"* ]] || args+=(--add-label "$label")
    elif [[ ",$current," == *",$label,"* ]]; then
      args+=(--remove-label "$label")
    fi
  done
  if [[ ${#args[@]} -gt ${#base[@]} ]]; then
    gh "${args[@]}" || true
  fi
  return 0
}
