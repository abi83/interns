#!/usr/bin/env bash
#
# Best-effort presence check for the pipeline's secrets and App-id variables
# (reviewer *and* coder GitHub App identities). Their values can't be set
# from here, so a definitively missing one is a hard failure with
# instructions; if the token can't even list them, that's a warning, not a
# failure, since GITHUB_TOKEN is never granted the scope to list secrets.
#
# Branch protection and GitHub Pages are checked elsewhere: both need admin
# access to read or write, which GITHUB_TOKEN can never be granted, so
# interns-install checks and fixes them locally at install time, with the
# operator's own admin-scoped `gh` session, before this script ever runs.
#
# Usage: safety-checks.sh
# Env:   GH_TOKEN            repo token
#        GITHUB_REPOSITORY   owner/name
#        REQUIRED_SECRETS      space-separated override of the secret list
#        REQUIRED_VARS         space-separated override of the Actions-var list

set -euo pipefail

REQUIRED_SECRETS="${REQUIRED_SECRETS:-CLAUDE_CODE_OAUTH_TOKEN INTERNS_REVIEWER_APP_PRIVATE_KEY INTERNS_CODER_APP_PRIVATE_KEY}"
REQUIRED_VARS="${REQUIRED_VARS:-INTERNS_REVIEWER_APP_ID INTERNS_CODER_APP_ID}"

: "${GH_TOKEN:?safety-checks: GH_TOKEN unset}"
: "${GITHUB_REPOSITORY:?safety-checks: GITHUB_REPOSITORY unset}"

say()  { echo "safety-checks: $*"; }
fail() { failures+=("$*"); echo "safety-checks: FAIL: $*" >&2; }

failures=()

api() { gh api -H "Accept: application/vnd.github+json" "$@"; }

check_secrets() {
  local present name missing=()
  # One list call: the default GITHUB_TOKEN can't read secrets, so treat an
  # outright failure as "can't verify" (a warning) rather than "all missing".
  if ! present=$(api "repos/$GITHUB_REPOSITORY/actions/secrets" \
      --paginate --jq '.secrets[].name' 2>/dev/null); then
    say "WARNING: can't list repo secrets (token lacks the scope) -- verify manually: $REQUIRED_SECRETS"
    return
  fi
  for name in $REQUIRED_SECRETS; do
    grep -qxF "$name" <<<"$present" || missing+=("$name")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    fail "missing repo secret(s): ${missing[*]} -- add them under Settings > Secrets and variables > Actions"
  else
    say "required secrets present: $REQUIRED_SECRETS"
  fi
}

check_vars() {
  local present name missing=()
  # Mirrors check_secrets: the default GITHUB_TOKEN can't read Actions
  # variables either, so a failed list is "can't verify", not "all missing".
  if ! present=$(api "repos/$GITHUB_REPOSITORY/actions/variables" \
      --paginate --jq '.variables[].name' 2>/dev/null); then
    say "WARNING: can't list repo variables (token lacks the scope) -- verify manually: $REQUIRED_VARS"
    return
  fi
  for name in $REQUIRED_VARS; do
    grep -qxF "$name" <<<"$present" || missing+=("$name")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    fail "missing repo variable(s): ${missing[*]} -- add them under Settings > Secrets and variables > Actions"
  else
    say "required variables present: $REQUIRED_VARS"
  fi
}

check_secrets
check_vars

if [[ ${#failures[@]} -gt 0 ]]; then
  echo >&2
  say "${#failures[@]} safety check(s) failed -- install aborted" >&2
  exit 1
fi
say "all safety checks passed"
