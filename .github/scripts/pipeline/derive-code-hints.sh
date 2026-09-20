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
#
# pipeline/src/pipeline/derive_code_hints.py is the only place this logic
# lives (interns#159) -- this is a thin shim that shells out to it.

set -euo pipefail

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.derive_code_hints "$@"
