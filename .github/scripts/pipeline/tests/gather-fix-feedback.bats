setup() {
  load helpers
  setup_stubs
}

@test "errors when no PR number is given" {
  run "$PIPELINE_DIR/gather-fix-feedback.sh" "" some-branch 5
  [ "$status" -eq 1 ]
  [[ "$output" == *"no open PR references issue #5"* ]]
}

@test "errors when there is no CHANGES_REQUESTED review" {
  export STUB_LAST_STATE=""
  run "$PIPELINE_DIR/gather-fix-feedback.sh" 6 feature-x 5
  [ "$status" -eq 1 ]
  [[ "$output" == *"no CHANGES_REQUESTED review found"* ]]
}

@test "checks out the branch and writes a feedback block to GITHUB_OUTPUT" {
  export STUB_LAST_STATE='{"id":123,"submitted_at":"2026-01-02T03:04:05Z","body":"do the thing"}'
  run "$PIPELINE_DIR/gather-fix-feedback.sh" 6 feature-x 5
  [ "$status" -eq 0 ]
  grep -q 'git fetch origin feature-x' "$STUB_LOG"
  grep -q 'git checkout feature-x' "$STUB_LOG"
  grep -qx 'text<<EOF_FEEDBACK' "$GITHUB_OUTPUT"
  grep -q 'Latest REQUEST_CHANGES review — 2026-01-02T03:04:05Z' "$GITHUB_OUTPUT"
  grep -qx 'EOF_FEEDBACK' "$GITHUB_OUTPUT"
}
