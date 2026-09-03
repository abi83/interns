#!/usr/bin/env bats
#
# Tests for sync-labels.sh — a PATH-shadowing `gh` stub records every call and
# serves a canned `gh label list` payload from $STUB_LABEL_LIST.

setup() {
  SCRIPT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)/sync-labels.sh"
  STUB_BIN="$BATS_TEST_TMPDIR/bin"
  STUB_LOG="$BATS_TEST_TMPDIR/calls.log"
  mkdir -p "$STUB_BIN"
  : >"$STUB_LOG"

  cat >"$STUB_BIN/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "gh $*" >>"$STUB_LOG"
if [[ "$1 $2" == "label list" ]]; then
  echo "${STUB_LABEL_LIST:-[]}"
fi
exit 0
EOF
  chmod +x "$STUB_BIN/gh"
  PATH="$STUB_BIN:$PATH"
  export STUB_LOG

  export GH_TOKEN=x GITHUB_REPOSITORY=owner/repo
  MANIFEST="$BATS_TEST_TMPDIR/labels.json"
  cat >"$MANIFEST" <<'EOF'
{ "version": 7, "labels": [
  { "name": "status:ready", "color": "0e8a16", "description": "go" },
  { "name": "pr:coding", "color": "0e8a16", "description": "on it" }
] }
EOF
}

calls() { cat "$STUB_LOG"; }

@test "creates every label when the repo has none" {
  export STUB_LABEL_LIST='[]'
  run "$SCRIPT" "$MANIFEST"
  [ "$status" -eq 0 ]
  [[ "$(calls)" == *"label create status:ready --repo owner/repo --color 0e8a16 --description go"* ]]
  [[ "$(calls)" == *"label create pr:coding "* ]]
  [[ "$output" == *"2 created, 0 updated, 0 unchanged"* ]]
}

@test "updates a drifted label and leaves a matching one alone" {
  export STUB_LABEL_LIST='[
    {"name":"status:ready","color":"cccccc","description":"go"},
    {"name":"pr:coding","color":"0e8a16","description":"on it"}
  ]'
  run "$SCRIPT" "$MANIFEST"
  [ "$status" -eq 0 ]
  [[ "$(calls)" == *"label edit status:ready --repo owner/repo --color 0e8a16 --description go"* ]]
  [[ "$(calls)" != *"label edit pr:coding"* ]]
  [[ "$(calls)" != *"label create"* ]]
  [[ "$output" == *"0 created, 1 updated, 1 unchanged"* ]]
}

@test "case-insensitive colour compare — no spurious update" {
  export STUB_LABEL_LIST='[
    {"name":"status:ready","color":"0E8A16","description":"go"},
    {"name":"pr:coding","color":"0e8a16","description":"on it"}
  ]'
  run "$SCRIPT" "$MANIFEST"
  [ "$status" -eq 0 ]
  [[ "$(calls)" != *"label edit"* ]]
  [[ "$output" == *"0 created, 0 updated, 2 unchanged"* ]]
}

@test "fails on a malformed manifest" {
  echo '{ "nope": true }' >"$MANIFEST"
  run "$SCRIPT" "$MANIFEST"
  [ "$status" -ne 0 ]
  [[ "$output" == *"malformed manifest"* ]]
}

@test "fails when GH_TOKEN is unset" {
  unset GH_TOKEN
  run "$SCRIPT" "$MANIFEST"
  [ "$status" -ne 0 ]
}
