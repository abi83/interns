#!/usr/bin/env bash
#
# Installer safety gate. The pipeline runs with the consumer repo's own
# credentials, so before the first run three things must hold:
#
#   1. The default branch is protected against direct pushes, so no agent
#      identity can land code without a human-approved PR. Created with a
#      baseline (require a PR, 1 approval, no force pushes/deletions) when
#      absent -- unless `allow_agent_push_to_default_branch: true` in the
#      config opts out.
#   2. The pipeline's secrets exist. Their values can't be set from here, so a
#      definitively missing one is a hard failure with instructions.
#   3. GitHub Pages is enabled (the dashboard's deploy target). Switched on
#      with the "GitHub Actions" build type when absent.
#
# Every check is reported; the script exits non-zero if any of them fails or
# can't be repaired, and the installer step then fails with it.
#
# Managing branch protection and listing secrets need more than the default
# GITHUB_TOKEN grants. Pass a token with repo-admin scope as GH_TOKEN to have
# those checks enforced; without it they report what they can and warn where
# they're blind, but a definitively unprotected branch or a definitively
# missing secret is still a hard failure.
#
# Usage: safety-checks.sh
# Env:   GH_TOKEN            repo token (admin scope enforces every check)
#        GITHUB_REPOSITORY   owner/name
#        AGENT_PIPELINE_CONFIG  config path (default .github/agent-pipeline.yml)
#        REQUIRED_SECRETS      space-separated override of the secret list
#        PIPELINE_BOT_LOGINS   space-separated extra bot logins to reject from
#                              a branch-protection push allowlist

set -euo pipefail

CONFIG="${AGENT_PIPELINE_CONFIG:-.github/agent-pipeline.yml}"
REQUIRED_SECRETS="${REQUIRED_SECRETS:-CLAUDE_CODE_OAUTH_TOKEN REVIEWER_APP_PRIVATE_KEY}"
# github-actions[bot] and claude[bot] both push branches during a run; neither
# (nor the reviewer App) may be granted a path to the default branch.
BOT_LOGINS="github-actions[bot] claude[bot] ${PIPELINE_BOT_LOGINS:-}"

: "${GH_TOKEN:?safety-checks: GH_TOKEN unset}"
: "${GITHUB_REPOSITORY:?safety-checks: GITHUB_REPOSITORY unset}"

say()  { echo "safety-checks: $*"; }
fail() { failures+=("$*"); echo "safety-checks: FAIL: $*" >&2; }

failures=()

api() { gh api -H "Accept: application/vnd.github+json" "$@"; }

# Run an api call, leaving the response body in $api_body and the outcome in
# $api_state: "ok" (2xx), "missing" (404), or "blocked" (anything else,
# typically a 403 from a token without the scope). Not run in a subshell, so
# both globals are visible to the caller.
api_body="" api_state=""
api_status() {
  local err
  err=$(mktemp)
  if api_body=$(api "$@" 2>"$err"); then
    api_state=ok
  elif grep -q 'HTTP 404' "$err"; then
    api_state=missing
  else
    api_state=blocked
  fi
  rm -f "$err"
}

config_allows_agent_push() {
  [[ -f "$CONFIG" ]] || return 1
  [[ "$(yq -r '.allow_agent_push_to_default_branch // false' "$CONFIG" 2>/dev/null)" == "true" ]]
}

check_branch_protection() {
  local branch granted bot ok=1
  branch=$(api "repos/$GITHUB_REPOSITORY" --jq '.default_branch') || {
    fail "could not read the default branch"
    return
  }

  api_status "repos/$GITHUB_REPOSITORY/branches/$branch/protection"
  case "$api_state" in
    ok)
      if [[ "$(jq -r '.required_pull_request_reviews // "null"' <<<"$api_body")" == "null" ]]; then
        fail "branch '$branch' is protected but does not require a pull request review"
        return
      fi
      granted=$(jq -r '
        [ (.restrictions.users[]?.login), ("@" + .restrictions.teams[]?.slug),
          (.restrictions.apps[]?.slug + "[bot]") ] | .[]' <<<"$api_body")
      for bot in $BOT_LOGINS; do
        if grep -qxF "$bot" <<<"$granted"; then
          fail "branch '$branch' push allowlist grants '$bot'"
          ok=0
        fi
      done
      if [[ "$ok" -eq 1 ]]; then say "branch protection on '$branch': ok"; fi
      return
      ;;
    blocked)
      fail "can't read branch protection for '$branch' -- GH_TOKEN needs repo-admin scope"
      return
      ;;
  esac

  # A definitive 404: the branch has no protection.
  if config_allows_agent_push; then
    say "branch '$branch' is unprotected; allow_agent_push_to_default_branch is set, skipping"
    return
  fi

  say "branch '$branch' is unprotected; applying the baseline"
  if api -X PUT "repos/$GITHUB_REPOSITORY/branches/$branch/protection" --input - >/dev/null <<'JSON'
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": { "required_approving_review_count": 1 },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
  then
    say "branch protection on '$branch': created"
  else
    fail "branch '$branch' is unprotected and the baseline could not be applied -- GH_TOKEN needs repo-admin scope"
  fi
}

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

check_pages() {
  api_status "repos/$GITHUB_REPOSITORY/pages"
  case "$api_state" in
    ok)      say "GitHub Pages: enabled"; return ;;
    blocked) fail "can't read GitHub Pages state -- GH_TOKEN needs 'pages' (or admin) scope"; return ;;
  esac
  say "GitHub Pages is off; enabling with the GitHub Actions build type"
  if api -X POST "repos/$GITHUB_REPOSITORY/pages" -f "build_type=workflow" >/dev/null 2>&1; then
    say "GitHub Pages: enabled"
  else
    fail "GitHub Pages could not be enabled -- turn it on under Settings > Pages"
  fi
}

check_branch_protection
check_secrets
check_pages

if [[ ${#failures[@]} -gt 0 ]]; then
  echo >&2
  say "${#failures[@]} safety check(s) failed -- install aborted" >&2
  exit 1
fi
say "all safety checks passed"
