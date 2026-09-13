#!/usr/bin/env bash
#
# Concatenates one or more prompt files and writes the result to
# $GITHUB_OUTPUT as `text`, so a workflow can inline real instructions
# straight into a Claude prompt instead of telling the agent to Read them
# itself -- the agent otherwise burns a guaranteed tool call per file just to
# learn its own task, every run (see abi83/interns#98's investigation).
#
# Usage: load-prompt.sh <file> [<file> ...]

set -euo pipefail

{
  echo 'text<<EOF_PROMPT_TEXT'
  cat "$@"
  echo 'EOF_PROMPT_TEXT'
} >> "$GITHUB_OUTPUT"
