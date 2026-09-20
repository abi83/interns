#!/usr/bin/env bash
#
# Resolve the section skeleton the refiner rewrites an issue body into, in
# code rather than by globbing paths in the prompt. For each refineable issue
# type it picks one template — the consumer repo's
# `.github/ISSUE_TEMPLATE/<type>.md` when present, otherwise the built-in
# `templates/issue/<type>.md` — drops the YAML frontmatter and HTML comments,
# and emits the headings in order. The refiner picks the type, then rewrites
# into the matching block; it never resolves a path itself.
#
# Appends `skeleton` to $GITHUB_OUTPUT: one block per type, each headed by the
# `type:<name>` label and followed by that template's heading lines.
#
# Env:
#   BUILTIN_DIR   dir holding the built-in templates/issue/<type>.md (required)
#   CONSUMER_DIR  dir checked for per-type overrides (default .github/ISSUE_TEMPLATE)
#   TYPES         space-separated type names (default "coding-task bug spike")
#
# pipeline/src/pipeline/resolve_issue_template.py is the only place this
# logic lives (interns#159) -- this is a thin shim that shells out to it.

set -euo pipefail

: "${BUILTIN_DIR:?BUILTIN_DIR not set}"

args=(--builtin-dir "$BUILTIN_DIR")
[[ -n "${CONSUMER_DIR:-}" ]] && args+=(--consumer-dir "$CONSUMER_DIR")
[[ -n "${TYPES:-}" ]] && args+=(--types "$TYPES")

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.resolve_issue_template "${args[@]}"
