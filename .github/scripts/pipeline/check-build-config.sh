#!/usr/bin/env bash
#
# Detects whether the repo's Makefile (templates/config/Makefile as installed)
# still has the unfilled test/build stub, so the pipeline can nudge the repo
# owner on the issue instead of either failing every PR or saying nothing.
# Deterministic and independent of what the coder did or said this run -- it
# greps the Makefile on disk, it doesn't trust the agent's word for it.
#
# Usage: check-build-config.sh
#   Writes `configured=true|false` to $GITHUB_OUTPUT. false when there's no
#   Makefile at all, or the stub marker is still present in either target.
#
# Run from the repo root (the coder's checked-out working directory).

set -euo pipefail

MARKER="INTERNS: not configured"

if [[ -f Makefile ]] && ! grep -qF "$MARKER" Makefile; then
  echo "configured=true" >>"$GITHUB_OUTPUT"
else
  echo "configured=false" >>"$GITHUB_OUTPUT"
fi
