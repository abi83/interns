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

set -euo pipefail

builtin_dir="${BUILTIN_DIR:?BUILTIN_DIR not set}"
consumer_dir="${CONSUMER_DIR:-.github/ISSUE_TEMPLATE}"
read -ra types <<<"${TYPES:-coding-task bug spike}"

# Strip the leading YAML frontmatter block, then keep only markdown heading
# lines. HTML comments in these templates never start with `#`, so filtering
# to heading lines drops them for free.
headings() {
  awk '
    NR == 1 && $0 == "---" { fm = 1; next }
    fm && $0 == "---"      { fm = 0; next }
    fm                     { next }
    /^#{1,6} /             { print }
  ' "$1"
}

{
  echo 'skeleton<<EOF_SKELETON'
  for type in "${types[@]}"; do
    template="$builtin_dir/$type.md"
    [[ -f "$consumer_dir/$type.md" ]] && template="$consumer_dir/$type.md"
    [[ -f "$template" ]] || { echo "resolve-issue-template: no template for '$type'" >&2; exit 1; }

    echo "type:$type"
    headings "$template"
    echo
  done
  echo 'EOF_SKELETON'
} >>"${GITHUB_OUTPUT:?GITHUB_OUTPUT not set}"
