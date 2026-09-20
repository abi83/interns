#!/usr/bin/env bash
#
# Shared helpers for the pipeline scripts. Source it, don't execute:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
#
# Every helper reads the Actions env the workflow already exports:
# GITHUB_REPOSITORY, GITHUB_SERVER_URL, GITHUB_RUN_ID, GH_TOKEN.

set -euo pipefail

# pipeline/src/pipeline/labels.py owns the label/status state machine
# (interns#156), pipeline.verdict the reviewer-verdict/round queries and
# pipeline.execution the execution-log parsing (interns#157); everything
# below shells out to one of them.
_PIPELINE_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
_labels() {
  PYTHONPATH="$_PIPELINE_SRC" python3 -m pipeline.labels "$GITHUB_REPOSITORY" "$@"
}
_verdict() {
  PYTHONPATH="$_PIPELINE_SRC" python3 -m pipeline.verdict "$GITHUB_REPOSITORY" "$@"
}

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

# Value of a field on a claude-code-action execution file's `result` entry
# (e.g. total_cost_usd, num_turns, result), or empty for a missing/timed-out
# run.
result_field() {
  PYTHONPATH="$_PIPELINE_SRC" python3 -m pipeline.execution "$@"
}

# REVIEWER_BOT's verdict for the PR's current head: the state of their latest
# review, or empty when it's stale -- targets a commit an earlier round's fix
# already moved past.
verdict_for_head() {
  _verdict "$1" "$REVIEWER_BOT" verdict-for-head "$2"
}

# How many CHANGES_REQUESTED reviews REVIEWER_BOT has left on the PR,
# optionally excluding one against a given commit (e.g. this run's own
# verdict, already posted against the current head).
rounds_requested() {
  local pr="$1" exclude="${2:-}"
  if [[ -n "$exclude" ]]; then
    _verdict "$pr" "$REVIEWER_BOT" rounds-requested --exclude-commit "$exclude"
  else
    _verdict "$pr" "$REVIEWER_BOT" rounds-requested
  fi
}

# How many reviews REVIEWER_BOT has left on the PR in total, regardless of
# state or which commit they targeted.
review_count() {
  _verdict "$1" "$REVIEWER_BOT" review-count
}

# Comma-joined current labels, for the inline "read labels" call sites.
issue_labels_csv() {
  _labels issue-labels "$1"
}
pr_labels_csv() {
  _labels pr-labels "$1"
}

# Move an issue to one lifecycle status, removing whichever of the others it
# currently carries. The issue-pipeline's own labels (needs-refinement,
# refined, estimated) are left untouched.
set_issue_status() {
  _labels set-issue-status "$1" "$2"
}

# Add/remove specific issue labels, skipping a `--remove` that isn't present
# (which `gh` would otherwise reject).
edit_issue_labels() {
  local number="$1"; shift
  _labels edit-issue-labels "$number" "$@"
}

# Set the PR's pipeline label (which agent is on it now, or pr:needs-attention
# once escalated), or clear all of them when called with no label. Mutually
# exclusive — only the target survives, so a coder/reviewer pickup or a clear
# drops a stale pr:needs-attention.
set_pr_pipeline_label() {
  _labels set-pr-label "$1" "${2:-}"
}

# Mark a PR as stuck: the pipeline has escalated it to a human and no agent is
# working it. "list the PRs a human still needs to act on" is then just
# `gh pr list --label pr:needs-attention`. Cleared by the next pickup or APPROVE.
escalate_pr() {
  _labels escalate-pr "$1"
}
