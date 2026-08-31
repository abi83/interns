#!/usr/bin/env bash
#
# Acts on the reviewer's latest verdict on a PR.
#
# Issue status:* is coarse: status:in-progress for the whole run,
# status:needs-attention when a human is needed, closed on merge. There is no
# "approved" issue state — an approved PR is found via its native review state,
# and the pr:* label only marks which agent is currently working (none, once
# the reviewer is done). The fix-round decision is read from the verdict, not a
# label (#133).
#
# max_fix_rounds: how many automatic coder fix rounds a PR gets before the loop
# escalates to a human. Counts CHANGES_REQUESTED reviews (this run's verdict
# included). Distinct from agent-pipeline.yml's max_turns (turns inside one
# agent run) — this counts whole agent invocations across a PR, so it stays a
# workflow-behaviour constant here, not an execution limit in the config file.
#
# Usage: apply-verdict.sh <pr> <issue-or-empty>
#   Env: REVIEWER_BOT (login whose reviews count), GH_TOKEN

set -euo pipefail
# shellcheck source=.github/scripts/pipeline/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

max_fix_rounds=1

pr="$1"
issue="${2:-}"
repo="$GITHUB_REPOSITORY"
pr_url="${GITHUB_SERVER_URL}/${repo}/pull/${pr}"

last_state=$(gh api "repos/$repo/pulls/$pr/reviews" \
  --jq '[.[] | select(.user.login==env.REVIEWER_BOT)] | last | .state // empty')

case "$last_state" in
  APPROVED)
    set_pr_pipeline_label "$pr"
    if [[ -n "$issue" ]]; then
      gh issue comment "$issue" --repo "$repo" --body \
        "Reviewer approved [PR #$pr]($pr_url) — awaiting owner merge. Run: $(run_url)"
    fi
    ;;
  CHANGES_REQUESTED)
    rc_count=$(gh api "repos/$repo/pulls/$pr/reviews" \
      --jq '[.[] | select(.user.login==env.REVIEWER_BOT and .state=="CHANGES_REQUESTED")] | length')
    if [[ "$rc_count" -gt "$max_fix_rounds" ]]; then
      set_pr_pipeline_label "$pr"
      [[ -n "$issue" ]] && set_issue_status "$issue" status:needs-attention
      gh pr comment "$pr" --repo "$repo" --body \
        "Second review still requests changes — the automatic fix round didn't converge. Escalating to a human. See the run: $(run_url)"
    elif [[ -n "$issue" ]]; then
      set_pr_pipeline_label "$pr" pr:coding
      # GITHUB_TOKEN label edits don't fire workflow runs (anti-recursion), so
      # dispatch the coder explicitly as a fix round.
      gh workflow run code-pipeline.yml --repo "$repo" \
        --field phase=coder --field issue_number="$issue" --field fix_round=true
    else
      set_pr_pipeline_label "$pr"
      gh pr comment "$pr" --repo "$repo" --body \
        "Changes requested but this PR has no linked issue — can't dispatch a coder fix round automatically. See the run: $(run_url)"
    fi
    ;;
  *)
    set_pr_pipeline_label "$pr"
    [[ -n "$issue" ]] && set_issue_status "$issue" status:needs-attention
    gh pr comment "$pr" --repo "$repo" --body \
      "Review run completed without submitting a recognized verdict — likely stopped partway through. See the run: $(run_url)"
    ;;
esac
