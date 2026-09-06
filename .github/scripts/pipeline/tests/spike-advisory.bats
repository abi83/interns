setup() {
  load helpers
  setup_stubs
  export ISSUE=34
}

@test "posts the advisory on a type:spike issue" {
  export STUB_ISSUE_LABELS="type:spike,status:refined"
  run "$PIPELINE_DIR/spike-advisory.sh"
  [ "$status" -eq 0 ]
  grep -q 'gh issue comment 34 --repo owner/repo --body This is a spike; no coder picks it up' "$STUB_LOG"
}

@test "no-op on any other issue type" {
  export STUB_ISSUE_LABELS="type:coding-task,status:refined"
  run "$PIPELINE_DIR/spike-advisory.sh"
  [ "$status" -eq 0 ]
  ! grep -q 'gh issue comment' "$STUB_LOG"
}
