#!/usr/bin/env bash
#
# Best-effort presence check for the pipeline's secrets and Client-id variables
# (reviewer, coder *and* triage GitHub App identities). Their values can't be set
# from here, so a definitively missing one is a hard failure with
# instructions; if the token can't even list them, that's a warning, not a
# failure, since GITHUB_TOKEN is never granted the scope to list secrets.
#
# Branch protection and GitHub Pages need admin access GITHUB_TOKEN never
# has -- interns-install checks and fixes those locally instead (see
# installer/src/interns_install/safety.py).
#
# Usage: safety-checks.sh
# Env:   GH_TOKEN            repo token
#        GITHUB_REPOSITORY   owner/name
#        REQUIRED_SECRETS      space-separated override of the secret list
#        REQUIRED_VARS         space-separated override of the Actions-var list
#
# pipeline/src/pipeline/safety_checks.py is the only place this logic lives
# (interns#159) -- this is a thin shim that shells out to it.

set -euo pipefail

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.safety_checks
