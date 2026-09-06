setup() {
  load helpers
  setup_stubs
}

@test "merged PR: drops status:in-progress from the issue and clears the pr:* label" {
  export STUB_PR_LABELS="pr:in-review" STUB_ISSUE_LABELS="status:in-progress"
  run "$PIPELINE_DIR/handle-pr-closed.sh" 8 19 true
  [ "$status" -eq 0 ]
  grep -q 'gh pr edit 8 --repo owner/repo --remove-label pr:in-review' "$STUB_LOG"
  grep -q 'gh issue edit 19 --repo owner/repo --remove-label status:in-progress' "$STUB_LOG"
  ! grep -q 'gh issue comment' "$STUB_LOG"
}

@test "merged PR: no issue edit when status:in-progress is already gone" {
  export STUB_ISSUE_LABELS=""
  run "$PIPELINE_DIR/handle-pr-closed.sh" 8 19 true
  [ "$status" -eq 0 ]
  ! grep -q 'gh issue edit' "$STUB_LOG"
}

@test "closed unmerged PR: moves the issue to needs-attention and comments" {
  export STUB_PR_LABELS="pr:coding" STUB_ISSUE_LABELS="status:in-progress"
  run "$PIPELINE_DIR/handle-pr-closed.sh" 8 19 false
  [ "$status" -eq 0 ]
  grep -q 'gh pr edit 8 --repo owner/repo --remove-label pr:coding' "$STUB_LOG"
  grep -q 'gh issue edit 19 --repo owner/repo --add-label status:needs-attention --remove-label status:in-progress' "$STUB_LOG"
  grep -q 'gh issue comment 19 .* closed without merging' "$STUB_LOG"
}

@test "no linked issue: only clears the PR label" {
  export STUB_PR_LABELS="pr:in-review"
  run "$PIPELINE_DIR/handle-pr-closed.sh" 8 "" false
  [ "$status" -eq 0 ]
  grep -q 'gh pr edit 8 --repo owner/repo --remove-label pr:in-review' "$STUB_LOG"
  ! grep -q 'gh issue' "$STUB_LOG"
}

@test "missing merged arg defaults to the unmerged path" {
  export STUB_ISSUE_LABELS="status:in-progress"
  run "$PIPELINE_DIR/handle-pr-closed.sh" 8 19
  [ "$status" -eq 0 ]
  grep -q 'gh issue comment 19 .* closed without merging' "$STUB_LOG"
}
