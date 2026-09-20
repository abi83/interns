#!/usr/bin/env bash
#
# Resolves the effective execution limits for one agent job and appends them
# to $GITHUB_OUTPUT (model, max_turns, timeout_minutes, max_output_tokens,
# cost_warn_usd, disallowed_tools, wiki_enabled, wiki_repo). The workflow
# wires those into --model / --max-turns / --disallowedTools /
# CLAUDE_CODE_MAX_OUTPUT_TOKENS / the step timeout, passes cost_warn_usd to
# run-summary.sh, and uses wiki_enabled/wiki_repo to decide whether to check
# out a wiki.
#
# All parsing and validation of .github/interns.yml lives in
# pipeline/src/pipeline/config.py (interns#158), the file's only reader --
# this is a thin shim that shells out to it.
#
# A malformed file or an unknown agent/key exits non-zero; the job's
# `Flag failure` step then posts the standard "pipeline failed" comment.
#
# Usage: agent-config.sh <refiner|estimator|coder|reviewer>
# Env:   INTERNS_CONFIG  config path (default .github/interns.yml)

set -euo pipefail

agent="${1:?usage: agent-config.sh <refiner|estimator|coder|reviewer>}"

pipeline_src="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../pipeline/src" && pwd)"
PYTHONPATH="$pipeline_src" python3 -m pipeline.config agent-config "$agent" \
  >> "${GITHUB_OUTPUT:-/dev/stdout}"
