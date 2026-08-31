#!/usr/bin/env bash
#
# Writes a Markdown run summary to $GITHUB_STEP_SUMMARY so the Actions run page
# shows what an agent phase did without opening the turn-by-turn step log.
# Complements report-run.sh: same cost figure, but richer detail and on the run
# page only, never the ticket.
#
# Best-effort — never fails the job. Every gh lookup falls back to a plain line
# and the caller runs it with `if: always()`, so a summary lands even when the
# Claude step itself failed.
#
# Usage: run-summary.sh <phase> <execution-file> [--issue N] [--pr N]
#                       [--round initial|fix] [--cost-warn USD]
#   phase       Coder | Review | Refinement | Estimation
#   --round     Coder/Review only: whether this run is an initial pass or a fix round
#   --cost-warn append a ⚠️ line when the run cost exceeds this figure
#   execution-file may be empty/absent — a SIGKILLed (timed-out) agent step
#   leaves none; the summary then reports a timeout.
#   Env: GH_TOKEN; REVIEWER_BOT for the Review phase

set -euo pipefail
# shellcheck source=.github/scripts/pipeline/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

phase="$1"
exec_file="${2:-}"
shift 2

issue=""
pr=""
round=""
cost_warn=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --issue) issue="$2"; shift 2 ;;
    --pr) pr="$2"; shift 2 ;;
    --round) round="$2"; shift 2 ;;
    --cost-warn) cost_warn="$2"; shift 2 ;;
    *) echo "run-summary: unknown argument $1" >&2; exit 1 ;;
  esac
done

repo="$GITHUB_REPOSITORY"
summary="${GITHUB_STEP_SUMMARY:?run-summary: GITHUB_STEP_SUMMARY is not set}"

# --- execution-file fields (all optional; a failed run may have none) ----------
result_field() {
  [[ -f "$exec_file" ]] || return 0
  jq -r "[.[] | select(.type==\"result\")][0].$1 // empty" "$exec_file" 2>/dev/null || true
}
raw_cost=$(result_field total_cost_usd)
num_turns=$(result_field num_turns)
final_msg=$(result_field result)

emit() { printf '%s\n' "$1" >>"$summary"; }

emit_quote() {
  if [[ -z "$final_msg" ]]; then
    emit "> _No final message — the run produced no result output._"
    return
  fi
  while IFS= read -r line; do
    emit "> ${line}"
  done <<<"$final_msg"
}

# `gh` wrapper that never aborts the script.
gh_q() { gh "$@" 2>/dev/null || true; }

round_line() {
  case "$round" in
    fix)     echo "Fix round${1:+ $1}" ;;
    initial) echo "Initial implementation" ;;
    *)       echo "" ;;
  esac
}

emit "## $phase run"
emit ""

case "$phase" in
  Coder)
    title=$(gh_q issue view "$issue" --repo "$repo" --json title --jq .title)
    emit "**Issue:** [#$issue](${GITHUB_SERVER_URL}/${repo}/issues/${issue})${title:+ — $title}"

    fix_n=""
    last_flagged_sha=""
    if [[ "$round" == "fix" && -n "$pr" ]]; then
      fix_n=$(gh_q api "repos/$repo/pulls/$pr/reviews" \
        --jq '[.[] | select(.state=="CHANGES_REQUESTED")] | length')
      last_flagged_sha=$(gh_q api "repos/$repo/pulls/$pr/reviews" \
        --jq '[.[] | select(.state=="CHANGES_REQUESTED")] | last | .commit_id // empty')
    fi
    rl=$(round_line "$fix_n")
    [[ -n "$rl" ]] && emit "**Round:** $rl"

    # `pr` only resolves an already-open PR — for a fix round it says nothing
    # about whether this run pushed anything. Treat it as "updated" only when
    # the head has moved off the commit the reviewer flagged; otherwise the
    # run failed silently after the PR already existed (AC: show the block).
    if [[ -z "$pr" ]]; then
      emit "**Outcome:** ⚠️ No PR — see the final message below."
    elif [[ "$round" == "fix" ]]; then
      head_sha=$(gh_q pr view "$pr" --repo "$repo" --json headRefOid --jq .headRefOid)
      if [[ -n "$head_sha" && -n "$last_flagged_sha" && "$head_sha" != "$last_flagged_sha" ]]; then
        emit "**Outcome:** PR updated — [#$pr](${GITHUB_SERVER_URL}/${repo}/pull/${pr})"
      else
        emit "**Outcome:** ⚠️ No new commit pushed — see the final message below."
      fi
    else
      emit "**Outcome:** PR opened — [#$pr](${GITHUB_SERVER_URL}/${repo}/pull/${pr})"
    fi

    if [[ -n "$pr" ]]; then
      if names=$(gh pr diff "$pr" --repo "$repo" --name-only 2>/dev/null); then
        emit "**Files changed:** $(printf '%s\n' "$names" | grep -c . || true)"
      else
        emit "**Files changed:** unknown"
      fi
    fi
    ;;

  Review)
    title=$(gh_q pr view "$pr" --repo "$repo" --json title --jq .title)
    emit "**PR:** [#$pr](${GITHUB_SERVER_URL}/${repo}/pull/${pr})${title:+ — $title}"

    # This run's own verdict is already POSTed by the time we get here, so
    # count only CHANGES_REQUESTED reviews against *earlier* commits — a
    # review against the current head is this run's and isn't a prior round.
    head_sha=$(gh_q pr view "$pr" --repo "$repo" --json headRefOid --jq .headRefOid)
    rc_count=$(gh_q api "repos/$repo/pulls/$pr/reviews" \
      --jq "[.[] | select(.user.login==\"${REVIEWER_BOT:-}\" and .state==\"CHANGES_REQUESTED\" and .commit_id != \"${head_sha}\")] | length")
    if [[ -n "$rc_count" && "$rc_count" -gt 0 ]]; then
      emit "**Round:** re-review (after $rc_count changes-requested)"
    else
      emit "**Round:** initial review"
    fi

    # A verdict is this run's outcome only if it was submitted against the PR's
    # current head — otherwise it's a stale review from an earlier round and
    # this run submitted nothing (same headRefOid check as the Dedup step).
    last_state=$(gh_q api "repos/$repo/pulls/$pr/reviews" \
      --jq "[.[] | select(.user.login==\"${REVIEWER_BOT:-}\")] | last | .state // empty")
    last_sha=$(gh_q api "repos/$repo/pulls/$pr/reviews" \
      --jq "[.[] | select(.user.login==\"${REVIEWER_BOT:-}\")] | last | .commit_id // empty")
    if [[ -n "$head_sha" && -n "$last_sha" && "$head_sha" == "$last_sha" ]]; then
      case "$last_state" in
        APPROVED)          emit "**Outcome:** ✅ Approved" ;;
        CHANGES_REQUESTED) emit "**Outcome:** 🔴 Changes requested" ;;
        *)                 emit "**Outcome:** ⚠️ No verdict submitted — see the final message below." ;;
      esac
    else
      emit "**Outcome:** ⚠️ No verdict submitted — see the final message below."
    fi
    ;;

  Refinement)
    title=$(gh_q issue view "$issue" --repo "$repo" --json title --jq .title)
    emit "**Issue:** [#$issue](${GITHUB_SERVER_URL}/${repo}/issues/${issue})${title:+ — $title}"

    labels=",$(gh_q issue view "$issue" --repo "$repo" --json labels --jq '[.labels[].name] | join(",")'),"
    if [[ "$labels" == *",status:refined,"* ]]; then
      emit "**Outcome:** Body refined"
    elif [[ "$labels" == *",status:needs-attention,"* ]]; then
      emit "**Outcome:** ⚠️ Stopped for clarification — see the final message below."
    else
      emit "**Outcome:** ⚠️ Ended without a terminal state — see the final message below."
    fi
    ;;

  Estimation)
    title=$(gh_q issue view "$issue" --repo "$repo" --json title --jq .title)
    emit "**Issue:** [#$issue](${GITHUB_SERVER_URL}/${repo}/issues/${issue})${title:+ — $title}"

    labels=",$(gh_q issue view "$issue" --repo "$repo" --json labels --jq '[.labels[].name] | join(",")'),"
    size=$(sed -nE 's/.*,(size:[A-Z]+),.*/\1/p' <<<"$labels")
    if [[ -n "$size" ]]; then
      emit "**Outcome:** Estimate posted — \`$size\`"
    elif [[ "$labels" == *",status:needs-attention,"* ]]; then
      emit "**Outcome:** ⚠️ Stopped for clarification — see the final message below."
    else
      emit "**Outcome:** ⚠️ Ended without an estimate — see the final message below."
    fi
    ;;

  *)
    echo "run-summary: unknown phase $phase" >&2
    exit 1
    ;;
esac

if [[ ! -f "$exec_file" ]]; then
  emit ""
  emit "> _No execution file — the agent step was killed (timed out) before writing results._"
fi

cost_line="**Cost:** \$$(format_cost "$raw_cost")"
[[ -n "$num_turns" ]] && cost_line+=" · ${num_turns} turns"
emit "$cost_line"

if [[ -n "$raw_cost" && -n "$cost_warn" ]] \
  && awk -v c="$raw_cost" -v w="$cost_warn" 'BEGIN { exit !(c + 0 > w + 0) }'; then
  emit ""
  emit "⚠️ cost \$$(format_cost "$raw_cost") over the \$$(printf '%.2f' "$cost_warn") warn limit"
fi

emit "[Full run log]($(run_url))"
emit ""
emit "### Agent's final message"
emit ""
emit_quote
