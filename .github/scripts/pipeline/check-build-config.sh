#!/usr/bin/env bash
#
# Detects whether the repo's Makefile (templates/config/Makefile as installed)
# still has the unfilled test/build stub, so the pipeline can nudge the repo
# owner on the issue instead of either failing every PR or saying nothing.
# Deterministic and independent of what the coder did or said this run -- it
# greps the Makefile on disk, it doesn't trust the agent's word for it.
#
# pipeline/src/pipeline/check_build_config.py is the only place this logic
# lives (interns#159) -- this is a thin shim that shells out to it.
#
# Usage: check-build-config.sh <repo-root>
#   Writes `configured=true|false` to $GITHUB_OUTPUT. false when there's no
#   Makefile at all, or the stub marker is still present in either target.

set -euo pipefail

repo_root="${1:?usage: check-build-config.sh <repo-root>}"

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.check_build_config "$repo_root"
