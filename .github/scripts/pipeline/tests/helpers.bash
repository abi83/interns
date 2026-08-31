# Test helpers: a PATH-shadowing `gh` (and `git`) stub that logs every
# invocation to $STUB_LOG and returns canned output driven by STUB_* env vars.

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

setup_stubs() {
  STUB_BIN="$BATS_TEST_TMPDIR/bin"
  STUB_LOG="$BATS_TEST_TMPDIR/calls.log"
  mkdir -p "$STUB_BIN"
  : >"$STUB_LOG"

  cat >"$STUB_BIN/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "gh $*" >>"$STUB_LOG"
case "$1 $2" in
  "issue view")
    case "$*" in
      *--json\ title*) echo "${STUB_ISSUE_TITLE-}" ;;
      *) echo "${STUB_ISSUE_LABELS-}" ;;
    esac ;;
  "pr view")
    case "$*" in
      *headRefOid*) echo "${STUB_HEAD_SHA-}" ;;
      *--json\ title*) echo "${STUB_PR_TITLE-}" ;;
      *) echo "${STUB_PR_LABELS-}" ;;
    esac ;;
  "pr checks") echo "${STUB_PR_CHECKS-[]}" ;;
  "pr diff") echo "${STUB_PR_FILES-}" ;;
esac
case "$1" in
  api)
    if [[ "$*" == *"/reviews"* && -n "${STUB_REVIEWS-}" ]]; then
      # Faithful path: run the real --jq expression against a reviews fixture.
      jqexpr=; shift
      while [[ $# -gt 0 ]]; do [[ "$1" == "--jq" ]] && { jqexpr="$2"; break; }; shift; done
      jq -r "$jqexpr" <<<"$STUB_REVIEWS"
    else
      case "$*" in
        *"| length"*) echo "${STUB_RC_COUNT-0}" ;;
        *commit_id*) echo "${STUB_LAST_SHA-}" ;;
        *) echo "${STUB_LAST_STATE-}" ;;
      esac
    fi ;;
esac
exit "${STUB_GH_EXIT-0}"
EOF

  cat >"$STUB_BIN/git" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "git $*" >>"$STUB_LOG"
exit 0
EOF

  chmod +x "$STUB_BIN/gh" "$STUB_BIN/git"
  PATH="$STUB_BIN:$PATH"

  export STUB_LOG
  export GITHUB_REPOSITORY="owner/repo"
  export GITHUB_SERVER_URL="https://github.com"
  export GITHUB_RUN_ID="42"
  export GITHUB_EVENT_NAME="pull_request"
  export GH_TOKEN="x"
  export GITHUB_OUTPUT="$BATS_TEST_TMPDIR/output"
  : >"$GITHUB_OUTPUT"
}

calls() { cat "$STUB_LOG"; }
