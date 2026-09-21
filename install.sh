#!/bin/sh
# interns installer bootstrap.
#
# The only shell in the install path: it runs before Python/uv exist. It
# ensures `uv` is present (via Astral's official installer) and then hands
# straight over to the Python CLI, which does the real work.
#
#   curl -LsSf https://raw.githubusercontent.com/abi83/interns/v0.1.0/install.sh | sh
#
# Args after `--` go to interns-install, e.g.
#   curl -LsSf .../install.sh | sh -s -- --dry-run --repo owner/name
#
# Override the version with INTERNS_REF (branch, tag or sha).

set -eu

# Exported so interns-install copies the install wrapper from the same ref.
export INTERNS_REF="${INTERNS_REF:-v0}"
REPO_URL="git+https://github.com/abi83/interns.git@${INTERNS_REF}"
SPEC="${REPO_URL}#subdirectory=installer"
# Pinned to the same ref as the installer: the installer imports its gh client
# from the pipeline package.
PIPELINE_SPEC="interns-pipeline @ ${REPO_URL}#subdirectory=pipeline"

if ! command -v uv >/dev/null 2>&1; then
  echo "bootstrap: installing uv (https://docs.astral.sh/uv/)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # uv lands in ~/.local/bin (or XDG_BIN_HOME); make it reachable for this run.
  export PATH="${XDG_BIN_HOME:-$HOME/.local/bin}:$HOME/.cargo/bin:$PATH"
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "bootstrap: the GitHub CLI (gh) is required and was not found." >&2
  echo "           install it from https://cli.github.com/ and run 'gh auth login'." >&2
  exit 1
fi

# `curl ... | sh` leaves stdin as the (now-exhausted) pipe carrying this
# script, not the terminal -- interns-install's prompts would hit EOF
# instantly and silently fall through to their defaults instead of waiting
# for an answer. Reattach stdin to the real terminal when one exists. Opening
# /dev/tty (not just its permission bits) can still fail with no controlling
# terminal at all (CI, some sandboxes) -- `exec 3< ...` in an `if` condition
# is exempt from `set -e`, so that case falls through instead of aborting.
if [ -t 0 ]; then
  exec uvx --from "$SPEC" --with "$PIPELINE_SPEC" interns-install "$@"
elif exec 3< /dev/tty 2>/dev/null; then
  exec uvx --from "$SPEC" --with "$PIPELINE_SPEC" interns-install "$@" <&3
else
  exec uvx --from "$SPEC" --with "$PIPELINE_SPEC" interns-install "$@"
fi
