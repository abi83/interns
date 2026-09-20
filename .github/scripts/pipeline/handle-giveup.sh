#!/usr/bin/env bash
#
# Runs after a coder fix round. If the agent left a ./.coder-gave-up.md sentinel
# it has *declined* the task — the feedback needs a protected path it can't
# push, is out of scope for the issue, or needs an owner decision — rather than
# pushing a fix. Escalate straight to a human instead of handing the PR back to
# the reviewer for a wasted round (#9).
#
# The coder step still exits 0 in this case (it's reporting, not failing), so
# without this check the workflow can't tell "gave up and commented" from
# "finished the fix" and would re-run the reviewer.
#
# Emits gave_up=true|false on $GITHUB_OUTPUT so the workflow skips the
# reviewer hand-off when the task was declined.
#
# Usage: handle-giveup.sh <issue> <pr-number-or-empty>
#
# pipeline/src/pipeline/handle_giveup.py is the only place this logic lives
# (interns#159) -- this is a thin shim that shells out to it.

set -euo pipefail

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.handle_giveup "$@"
