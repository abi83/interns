#!/usr/bin/env bash
#
# Deterministic issue-type gate, shared by the estimate and code jobs. An issue
# whose type:* label isn't in the accepted list never reaches an agent: post a
# comment, park the issue on status:needs-attention, and tell the calling job to
# skip its Claude step. Running a full agent invocation just to execute a fixed
# `if` on a label already present when the job starts is wasteful and fragile.
#
# Invoked by the gate-issue-type composite action, which passes everything in the
# environment:
#   GH_TOKEN, GITHUB_REPOSITORY, GITHUB_OUTPUT   standard Actions env
#   ISSUE           issue number
#   ACCEPTED        comma-separated type:* labels the calling job can handle
#   REMOVE_STATUS   status:* label to drop when parking a rejected issue
#   REJECT_COMMENT  comment body posted on a rejected issue

set -euo pipefail

labels=$(gh issue view "$ISSUE" --repo "$GITHUB_REPOSITORY" --json labels --jq '[.labels[].name] | join(",")')

IFS=',' read -ra want <<<"$ACCEPTED"
for type in "${want[@]}"; do
  if [[ ",$labels," == *",$type,"* ]]; then
    echo "Issue #$ISSUE is $type — accepted."
    echo "skip=false" >>"$GITHUB_OUTPUT"
    exit 0
  fi
done

echo "Issue #$ISSUE type is not one of {$ACCEPTED} (labels: $labels) — parking on status:needs-attention."
gh issue edit "$ISSUE" --repo "$GITHUB_REPOSITORY" \
  --add-label status:needs-attention --remove-label "$REMOVE_STATUS" || true
gh issue comment "$ISSUE" --repo "$GITHUB_REPOSITORY" --body "$REJECT_COMMENT"
echo "skip=true" >>"$GITHUB_OUTPUT"
