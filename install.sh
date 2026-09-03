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

INTERNS_REF="${INTERNS_REF:-v0.1.0}"
SPEC="git+https://github.com/abi83/interns.git@${INTERNS_REF}#subdirectory=installer"

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

exec uvx --from "$SPEC" interns-install "$@"
