#!/usr/bin/env bash
#
# Sync the versioned label manifest (.github/labels.json) into a repo,
# idempotently: create labels that are missing, update colour/description
# when they've drifted, leave everything else alone.
#
# Additive by design — a label that isn't in the manifest is never deleted,
# so a consumer's own labels survive a sync. Re-running with no manifest
# changes is a no-op.
#
# Usage: sync-labels.sh [manifest-file]   (default: .github/labels.json)
#
# Env: GH_TOKEN (issues: write), GITHUB_REPOSITORY.

set -euo pipefail

MANIFEST="${1:-.github/labels.json}"

die() { echo "sync-labels: $*" >&2; exit 1; }

[[ -f "$MANIFEST" ]] || die "no such manifest: $MANIFEST"
: "${GH_TOKEN:?sync-labels: GH_TOKEN unset}"
: "${GITHUB_REPOSITORY:?sync-labels: GITHUB_REPOSITORY unset}"

jq -e '(.version | type == "number") and (.labels | type == "array")' \
  "$MANIFEST" >/dev/null || die "malformed manifest: $MANIFEST"

version=$(jq -r '.version' "$MANIFEST")
existing=$(gh label list --repo "$GITHUB_REPOSITORY" --limit 500 \
  --json name,color,description)

created=0 updated=0 unchanged=0

while IFS=$'\t' read -r name color desc; do
  current=$(jq -c --arg n "$name" 'map(select(.name == $n)) | first // empty' \
    <<<"$existing")

  if [[ -z "$current" ]]; then
    gh label create "$name" --repo "$GITHUB_REPOSITORY" \
      --color "$color" --description "$desc"
    created=$((created + 1))
    continue
  fi

  cur_color=$(jq -r '.color' <<<"$current")
  cur_desc=$(jq -r '.description // ""' <<<"$current")
  if [[ "${cur_color,,}" == "${color,,}" && "$cur_desc" == "$desc" ]]; then
    unchanged=$((unchanged + 1))
    continue
  fi

  gh label edit "$name" --repo "$GITHUB_REPOSITORY" \
    --color "$color" --description "$desc"
  updated=$((updated + 1))
done < <(jq -r '.labels[] | [.name, .color, (.description // "")] | @tsv' "$MANIFEST")

echo "sync-labels: manifest v${version} -> ${GITHUB_REPOSITORY}: ${created} created, ${updated} updated, ${unchanged} unchanged"
