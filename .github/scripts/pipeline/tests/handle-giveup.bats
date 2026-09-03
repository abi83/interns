setup() {
  load helpers
  setup_stubs
  export GITHUB_WORKSPACE="$BATS_TEST_TMPDIR/ws"
  mkdir -p "$GITHUB_WORKSPACE"
}

@test "no sentinel: emits gave_up=false and does nothing" {
  run "$PIPELINE_DIR/handle-giveup.sh" 7 15
  [ "$status" -eq 0 ]
  grep -q '^gave_up=false$' "$GITHUB_OUTPUT"
  ! grep -q 'gh issue comment' "$STUB_LOG"
  ! grep -q 'gh issue edit' "$STUB_LOG"
}

@test "sentinel present: escalates the issue, clears the PR label, comments the reason" {
  export STUB_ISSUE_LABELS="status:in-progress"
  export STUB_PR_LABELS="pr:coding"
  printf 'Feedback needs a change under .github/workflows/ which I cannot push.\n' \
    >"$GITHUB_WORKSPACE/.coder-gave-up.md"

  run "$PIPELINE_DIR/handle-giveup.sh" 7 15
  [ "$status" -eq 0 ]
  grep -q '^gave_up=true$' "$GITHUB_OUTPUT"
  grep -q 'gh issue edit 7 --repo owner/repo --add-label status:needs-attention --remove-label status:in-progress' "$STUB_LOG"
  grep -q 'gh pr edit 15 --repo owner/repo --remove-label pr:coding' "$STUB_LOG"
  grep -q 'gh issue comment 7 .* declined this task' "$STUB_LOG"
  grep -q 'cannot push' "$STUB_LOG"
}

@test "sentinel present but empty: still escalates, with a placeholder reason" {
  export STUB_ISSUE_LABELS="status:in-progress"
  : >"$GITHUB_WORKSPACE/.coder-gave-up.md"

  run "$PIPELINE_DIR/handle-giveup.sh" 7 ""
  [ "$status" -eq 0 ]
  grep -q '^gave_up=true$' "$GITHUB_OUTPUT"
  grep -q 'no reason given' "$STUB_LOG"
  ! grep -q 'gh pr edit' "$STUB_LOG"
}
