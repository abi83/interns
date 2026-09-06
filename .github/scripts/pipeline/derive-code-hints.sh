#!/usr/bin/env bash
#
# Derives two deterministic hints for the initial coder run and writes them to
# $GITHUB_OUTPUT:
#   commit_type_hint  Conventional Commit prefix for the PR title (`fix:` / `feat:`)
#   branch            branch name `<prefix>/issue-<n>-<slug>` from the issue title
#
# Both are computable from the issue's type:* label and title before the agent
# starts, so the agent shouldn't spend reasoning inventing them. push-branch.sh
# squashes the branch on push, so the branch name is near-cosmetic. Runs after
# the issue-type gate, which guarantees a type:coding-task or type:bug label.
#
# Usage: derive-code-hints.sh <issue-number>

set -euo pipefail

ISSUE="$1"
REPO="$GITHUB_REPOSITORY"

labels=$(gh issue view "$ISSUE" --repo "$REPO" --json labels --jq '[.labels[].name] | join(",")')
title=$(gh issue view "$ISSUE" --repo "$REPO" --json title --jq .title)

if [[ ",$labels," == *",type:bug,"* ]]; then
  prefix=fix
elif [[ ",$labels," == *",type:coding-task,"* ]]; then
  prefix=feat
else
  echo "Error: issue #$ISSUE has neither type:bug nor type:coding-task (labels: $labels)" >&2
  exit 1
fi

slug=$(printf '%s' "$title" \
  | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//' \
  | cut -c1-40 \
  | sed -E 's/-+$//')

{
  echo "commit_type_hint=${prefix}:"
  echo "branch=${prefix}/issue-${ISSUE}-${slug}"
} >>"$GITHUB_OUTPUT"
