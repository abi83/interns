#!/usr/bin/env bash
#
# Copy the interns caller stubs + starter config into the current repo, but
# only files that don't already exist — a re-run never clobbers a hand-edited
# one. Optionally drop in the default issue templates when the repo has none.
#
# Usage: stage-stubs.sh <interns-checkout-dir> [install-issue-templates]
#   install-issue-templates: "true" to add templates/issue/* when the repo
#   has no .github/ISSUE_TEMPLATE/ (default: false)
#
# Emits `changed=<0|1>` to $GITHUB_OUTPUT (or stdout when unset).

set -euo pipefail

INTERNS_DIR="${1:?stage-stubs: interns checkout dir required}"
INSTALL_TEMPLATES="${2:-false}"

[[ -d "$INTERNS_DIR" ]] || { echo "stage-stubs: no such dir: $INTERNS_DIR" >&2; exit 1; }

changed=0

copy_if_absent() {
  local src="$1" dest="$2"
  if [[ -e "$dest" ]]; then
    echo "skip (exists): $dest"
    return
  fi
  mkdir -p "$(dirname "$dest")"
  cp "$src" "$dest"
  echo "add: $dest"
  changed=1
}

copy_if_absent "$INTERNS_DIR/templates/workflows/issue-pipeline.yml" .github/workflows/issue-pipeline.yml
copy_if_absent "$INTERNS_DIR/templates/workflows/code-pipeline.yml"  .github/workflows/code-pipeline.yml
copy_if_absent "$INTERNS_DIR/templates/config/agent-pipeline.yml"    .github/agent-pipeline.yml

if [[ "$INSTALL_TEMPLATES" == "true" && ! -d .github/ISSUE_TEMPLATE ]]; then
  mkdir -p .github/ISSUE_TEMPLATE
  cp "$INTERNS_DIR"/templates/issue/*.md "$INTERNS_DIR"/templates/issue/config.yml .github/ISSUE_TEMPLATE/
  echo "add: .github/ISSUE_TEMPLATE/ (from interns defaults)"
  changed=1
fi

echo "changed=$changed" >> "${GITHUB_OUTPUT:-/dev/stdout}"
