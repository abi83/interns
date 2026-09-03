#!/usr/bin/env bats
#
# Tests for safety-checks.sh — a PATH-shadowing `gh` stub logs every call and
# serves canned GitHub API responses driven by STUB_* env vars.

setup() {
  SCRIPT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)/safety-checks.sh"
  STUB_BIN="$BATS_TEST_TMPDIR/bin"
  STUB_LOG="$BATS_TEST_TMPDIR/calls.log"
  mkdir -p "$STUB_BIN"
  : >"$STUB_LOG"

  cat >"$STUB_BIN/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "gh $*" >>"$STUB_LOG"
args="$*"
notfound() { echo "gh: Not Found (HTTP 404)" >&2; exit 1; }
blocked()  { echo "gh: Resource not accessible by integration (HTTP 403)" >&2; exit 1; }
case "$args" in
  *"-X PUT"*"/protection"*)  exit "${STUB_PUT_EXIT:-0}" ;;
  *"-X POST"*"/pages"*)      exit "${STUB_PAGES_POST_EXIT:-0}" ;;
  *"/branches/"*"/protection"*)
    [[ "${STUB_PROTECTION_BLOCKED:-0}" == 1 ]] && blocked
    [[ -n "${STUB_PROTECTION:-}" ]] || notfound
    printf '%s' "$STUB_PROTECTION"; exit 0 ;;
  *"/actions/secrets"*)
    [[ "${STUB_SECRETS_LIST_FAIL:-0}" == 1 ]] && blocked
    printf '%s\n' ${STUB_SECRETS:-}; exit 0 ;;
  *"/actions/variables"*)
    [[ "${STUB_VARS_LIST_FAIL:-0}" == 1 ]] && blocked
    printf '%s\n' ${STUB_VARS:-}; exit 0 ;;
  *"/pages"*)
    [[ "${STUB_PAGES_BLOCKED:-0}" == 1 ]] && blocked
    [[ "${STUB_PAGES_ON:-0}" == 1 ]] && exit 0
    notfound ;;
  *"repos/owner/repo"*)
    printf '%s' "${STUB_DEFAULT_BRANCH:-main}"; exit 0 ;;
esac
exit 0
EOF
  chmod +x "$STUB_BIN/gh"
  PATH="$STUB_BIN:$PATH"
  export STUB_LOG

  export GH_TOKEN=x GITHUB_REPOSITORY=owner/repo
  export AGENT_PIPELINE_CONFIG="$BATS_TEST_TMPDIR/agent-pipeline.yml"

  # Happy-path defaults; individual tests override.
  export STUB_PROTECTION='{"required_pull_request_reviews":{"required_approving_review_count":1},"restrictions":null}'
  export STUB_SECRETS="CLAUDE_CODE_OAUTH_TOKEN REVIEWER_APP_PRIVATE_KEY CODER_APP_PRIVATE_KEY"
  export STUB_VARS="REVIEWER_APP_ID CODER_APP_ID"
  export STUB_PAGES_ON=1
}

calls() { cat "$STUB_LOG"; }

@test "passes when protection, secrets and Pages are all in place" {
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"all safety checks passed"* ]]
  [[ "$(calls)" != *"-X PUT"* ]]
  [[ "$(calls)" != *"-X POST"* ]]
}

@test "applies the baseline when the default branch is unprotected" {
  unset STUB_PROTECTION
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$(calls)" == *"-X PUT repos/owner/repo/branches/main/protection"* ]]
  [[ "$output" == *"branch protection on 'main': created"* ]]
}

@test "fails when the branch is unprotected and the baseline cannot be applied" {
  unset STUB_PROTECTION
  export STUB_PUT_EXIT=1
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"baseline could not be applied"* ]]
}

@test "skips the baseline when the config opts out" {
  unset STUB_PROTECTION
  printf 'allow_agent_push_to_default_branch: true\n' >"$AGENT_PIPELINE_CONFIG"
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$(calls)" != *"-X PUT"* ]]
  [[ "$output" == *"skipping"* ]]
}

@test "fails when branch protection can't be read (token lacks admin)" {
  export STUB_PROTECTION_BLOCKED=1
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"can't read branch protection"* ]]
  [[ "$(calls)" != *"-X PUT"* ]]
}

@test "fails when Pages state can't be read (token lacks scope)" {
  export STUB_PAGES_BLOCKED=1
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"can't read GitHub Pages state"* ]]
  [[ "$(calls)" != *"-X POST"* ]]
}

@test "fails when protection does not require a pull request review" {
  export STUB_PROTECTION='{"required_pull_request_reviews":null,"restrictions":null}'
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"does not require a pull request review"* ]]
}

@test "fails when a bot identity is on the push allowlist" {
  export STUB_PROTECTION='{"required_pull_request_reviews":{"required_approving_review_count":1},"restrictions":{"users":[{"login":"github-actions[bot]"}],"teams":[],"apps":[]}}'
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"grants 'github-actions[bot]'"* ]]
}

@test "fails and names a missing secret" {
  export STUB_SECRETS="CLAUDE_CODE_OAUTH_TOKEN"
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"missing repo secret(s): REVIEWER_APP_PRIVATE_KEY CODER_APP_PRIVATE_KEY"* ]]
}

@test "warns but does not fail when secrets can't be listed" {
  export STUB_SECRETS_LIST_FAIL=1
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"WARNING: can't list repo secrets"* ]]
}

@test "fails and names a missing Actions variable" {
  export STUB_VARS="REVIEWER_APP_ID"
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"missing repo variable(s): CODER_APP_ID"* ]]
}

@test "warns but does not fail when variables can't be listed" {
  export STUB_VARS_LIST_FAIL=1
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"WARNING: can't list repo variables"* ]]
}

@test "enables Pages when it is off" {
  export STUB_PAGES_ON=0
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$(calls)" == *"-X POST repos/owner/repo/pages"* ]]
  [[ "$output" == *"GitHub Pages: enabled"* ]]
}

@test "fails when Pages cannot be enabled" {
  export STUB_PAGES_ON=0 STUB_PAGES_POST_EXIT=1
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"Pages could not be enabled"* ]]
}

@test "reports every failure, not just the first" {
  unset STUB_PROTECTION
  export STUB_PUT_EXIT=1 STUB_SECRETS="" STUB_PAGES_ON=0 STUB_PAGES_POST_EXIT=1
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"3 safety check(s) failed"* ]]
}

@test "fails when GH_TOKEN is unset" {
  unset GH_TOKEN
  run "$SCRIPT"
  [ "$status" -ne 0 ]
}
