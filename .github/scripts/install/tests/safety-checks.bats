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
blocked()  { echo "gh: Resource not accessible by integration (HTTP 403)" >&2; exit 1; }
case "$args" in
  *"/actions/secrets"*)
    [[ "${STUB_SECRETS_LIST_FAIL:-0}" == 1 ]] && blocked
    printf '%s\n' ${STUB_SECRETS:-}; exit 0 ;;
  *"/actions/variables"*)
    [[ "${STUB_VARS_LIST_FAIL:-0}" == 1 ]] && blocked
    printf '%s\n' ${STUB_VARS:-}; exit 0 ;;
esac
exit 0
EOF
  chmod +x "$STUB_BIN/gh"
  PATH="$STUB_BIN:$PATH"
  export STUB_LOG

  export GH_TOKEN=x GITHUB_REPOSITORY=owner/repo

  # Happy-path defaults; individual tests override.
  export STUB_SECRETS="CLAUDE_CODE_OAUTH_TOKEN INTERNS_REVIEWER_APP_PRIVATE_KEY INTERNS_CODER_APP_PRIVATE_KEY"
  export STUB_VARS="INTERNS_REVIEWER_APP_ID INTERNS_CODER_APP_ID"
}

calls() { cat "$STUB_LOG"; }

@test "passes when secrets and variables are all present" {
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"all safety checks passed"* ]]
}

@test "fails and names a missing secret" {
  export STUB_SECRETS="CLAUDE_CODE_OAUTH_TOKEN"
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"missing repo secret(s): INTERNS_REVIEWER_APP_PRIVATE_KEY INTERNS_CODER_APP_PRIVATE_KEY"* ]]
}

@test "warns but does not fail when secrets can't be listed" {
  export STUB_SECRETS_LIST_FAIL=1
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"WARNING: can't list repo secrets"* ]]
}

@test "fails and names a missing Actions variable" {
  export STUB_VARS="INTERNS_REVIEWER_APP_ID"
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"missing repo variable(s): INTERNS_CODER_APP_ID"* ]]
}

@test "warns but does not fail when variables can't be listed" {
  export STUB_VARS_LIST_FAIL=1
  run "$SCRIPT"
  [ "$status" -eq 0 ]
  [[ "$output" == *"WARNING: can't list repo variables"* ]]
}

@test "reports every failure, not just the first" {
  export STUB_SECRETS="" STUB_VARS=""
  run "$SCRIPT"
  [ "$status" -ne 0 ]
  [[ "$output" == *"2 safety check(s) failed"* ]]
}

@test "fails when GH_TOKEN is unset" {
  unset GH_TOKEN
  run "$SCRIPT"
  [ "$status" -ne 0 ]
}
