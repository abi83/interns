setup() {
  load helpers
  setup_stubs
}

@test "hands the PR to the reviewer when one exists" {
  export STUB_PR_LABELS="pr:coding"
  run "$PIPELINE_DIR/handoff-to-review.sh" 7 15
  [ "$status" -eq 0 ]
  grep -q 'gh pr edit 15 --repo owner/repo --remove-label pr:coding --add-label pr:in-review' "$STUB_LOG"
  ! grep -q 'gh issue' "$STUB_LOG"
}

@test "flags the issue when the coder left no PR" {
  export STUB_ISSUE_LABELS="status:in-progress"
  run "$PIPELINE_DIR/handoff-to-review.sh" 7 ""
  grep -q 'gh issue edit 7 --repo owner/repo --add-label status:needs-attention --remove-label status:in-progress' "$STUB_LOG"
  grep -q 'gh issue comment 7 .* without leaving an open PR referencing this issue' "$STUB_LOG"
}
