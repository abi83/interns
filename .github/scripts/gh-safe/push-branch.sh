#!/usr/bin/env bash
#
# Squashes the current branch to one commit and pushes it to origin.
# Arguments are ignored, so untrusted prompt text can't steer this into
# --force over main, a different remote, or an explicit refspec.
#
# Squash before the guard, not after: squashing collapses an
# intermediate-only edit to a protected path, and the guard is the
# backstop for a net change that really touches one.

set -euo pipefail

PROTECTED_PATHS_RE='^\.github/(workflows|scripts/(gh-safe|pipeline))/'

BRANCH=$(git rev-parse --abbrev-ref HEAD)

case "$BRANCH" in
  main|master)
    echo "Error: refusing to push $BRANCH directly" >&2
    exit 1
    ;;
esac

git fetch origin main --quiet
BASE=$(git merge-base origin/main HEAD)

if [ "$BASE" = "$(git rev-parse HEAD)" ]; then
  echo "Error: no commits beyond origin/main — nothing to push" >&2
  exit 1
fi

MESSAGE=$(git log -1 --format=%B)
git reset --soft "$BASE"
git commit --quiet -m "$MESSAGE"

PROTECTED=$(git diff-tree --no-commit-id --name-only -r HEAD | grep -E "$PROTECTED_PATHS_RE" || true)

if [ -n "$PROTECTED" ]; then
  echo "Error: you are not allowed to change these paths (they define this pipeline's own sandbox):" >&2
  while IFS= read -r path; do echo "  $path" >&2; done <<< "$PROTECTED"
  echo "Drop these edits and push again." >&2
  exit 1
fi

git push --force-with-lease -u origin "$BRANCH"
