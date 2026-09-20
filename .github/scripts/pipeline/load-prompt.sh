#!/usr/bin/env bash
#
# Concatenates one or more prompt files and writes the result to
# $GITHUB_OUTPUT as `text`, so a workflow can inline real instructions
# straight into a Claude prompt instead of telling the agent to Read them
# itself -- the agent otherwise burns a guaranteed tool call per file just to
# learn its own task, every run (see abi83/interns#98's investigation).
#
# pipeline/src/pipeline/prompt.py is the only place this logic lives
# (interns#159) -- this is a thin shim that shells out to it.
#
# Usage: load-prompt.sh <file> [<file> ...]

set -euo pipefail

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.prompt "$@"
