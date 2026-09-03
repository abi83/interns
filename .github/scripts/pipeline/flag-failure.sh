#!/usr/bin/env bash
#
# Common failure handler for the agent phases: send the issue to
# status:needs-attention, mark the PR pr:needs-attention (or just clear its
# label on a fix-round crash, which escalates issue-side), and post a comment
# linking the run.
#
# Usage: flag-failure.sh --noun <noun> [--issue N] [--pr N] [--fix-round]
#   --noun       verb for the standard comment ("Automated <noun> failed.")
#   --issue      issue to move to needs-attention / comment on
#   --pr         PR to clear labels on / comment on
#   --fix-round  coder fix-round: comment on the issue with the re-dispatch
#                command instead of the standard message

set -euo pipefail
# shellcheck source=.github/scripts/pipeline/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

noun=""
issue=""
pr=""
fix_round=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --noun) noun="$2"; shift 2 ;;
    --issue) issue="$2"; shift 2 ;;
    --pr) pr="$2"; shift 2 ;;
    --fix-round) fix_round=true; shift ;;
    *) echo "flag-failure: unknown argument $1" >&2; exit 1 ;;
  esac
done

# A review-job crash leaves the PR stuck with no verdict; mark it for a human.
# A fix-round crash escalates on the issue side, so the PR just loses its label.
if [[ -n "$pr" ]]; then
  if [[ "$fix_round" == true ]]; then
    set_pr_pipeline_label "$pr"
  else
    escalate_pr "$pr"
  fi
fi
if [[ -n "$issue" ]]; then
  set_issue_status "$issue" status:needs-attention
fi

if [[ "$fix_round" == true ]]; then
  gh issue comment "$issue" --repo "$GITHUB_REPOSITORY" --body \
    "Automated fix round failed — issue set to \`status:needs-attention\`. Re-dispatch once the cause is addressed: \`gh workflow run code-pipeline.yml -f phase=coder -f issue_number=$issue -f fix_round=true\`. Run: $(run_url)"
  exit 0
fi

body="Automated $noun failed. See the run: $(run_url)"
if [[ -n "$pr" ]]; then
  gh pr comment "$pr" --repo "$GITHUB_REPOSITORY" --body "$body"
else
  gh issue comment "$issue" --repo "$GITHUB_REPOSITORY" --body "$body"
fi
