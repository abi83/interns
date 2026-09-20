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
#
# pipeline/src/pipeline/sync_labels.py is the only place this logic lives
# (interns#159) -- this is a thin shim that shells out to it.

set -euo pipefail

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.sync_labels "$@"
