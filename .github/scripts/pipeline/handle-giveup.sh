#!/usr/bin/env bash
#
# Runs after a coder fix round. If the agent left a ./.coder-gave-up.md sentinel
# it has *declined* the task — the feedback needs a protected path it can't
# push, is out of scope for the issue, or needs an owner decision — rather than
# pushing a fix. Escalate straight to a human instead of handing the PR back to
# the reviewer for a wasted round (#9).
#
# The coder step still exits 0 in this case (it's reporting, not failing), so
# without this check the workflow can't tell "gave up and commented" from
# "finished the fix" and would re-run the reviewer.
#
# Emits gave_up=true|false on $GITHUB_OUTPUT so the workflow skips the reviewer
# hand-off when the task was declined.
#
# Usage: handle-giveup.sh <issue> <pr-number-or-empty>

set -euo pipefail
# shellcheck source=.github/scripts/pipeline/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

issue="$1"
pr="${2:-}"
sentinel="${GITHUB_WORKSPACE:-.}/.coder-gave-up.md"
out="${GITHUB_OUTPUT:-/dev/null}"

if [[ ! -f "$sentinel" ]]; then
  echo "gave_up=false" >>"$out"
  exit 0
fi

reason="$(cat "$sentinel")"
[[ -n "${reason//[[:space:]]/}" ]] || reason="_(no reason given)_"

if [[ -n "$pr" ]]; then
  set_pr_pipeline_label "$pr"
fi
set_issue_status "$issue" status:needs-attention

gh issue comment "$issue" --repo "$GITHUB_REPOSITORY" --body \
"The coder fix round declined this task and set \`status:needs-attention\` — it was not handed back to the reviewer.

$reason

Run: $(run_url)"

echo "gave_up=true" >>"$out"
