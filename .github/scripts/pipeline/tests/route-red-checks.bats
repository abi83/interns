setup() {
  load helpers
  setup_stubs
}

@test "clears the pr label, comments, and flags the linked issue" {
  export STUB_PR_LABELS="pr:in-review" STUB_ISSUE_LABELS="status:in-progress"
  run "$PIPELINE_DIR/route-red-checks.sh" 8 19 '`test`=fail, `build`=pass'
  [ "$status" -eq 0 ]
  grep -q 'gh pr edit 8 --repo owner/repo --remove-label pr:in-review' "$STUB_LOG"
  grep -q 'gh pr comment 8 .* Required checks are not green (`test`=fail, `build`=pass)' "$STUB_LOG"
  grep -q 'gh issue edit 19 --repo owner/repo --add-label status:needs-attention --remove-label status:in-progress' "$STUB_LOG"
}

@test "skips the issue edit when there is no linked issue" {
  run "$PIPELINE_DIR/route-red-checks.sh" 8 "" 'timed out'
  [ "$status" -eq 0 ]
  ! grep -q 'gh issue' "$STUB_LOG"
}
