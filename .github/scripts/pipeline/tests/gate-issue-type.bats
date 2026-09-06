setup() {
  load helpers
  setup_stubs
  export ISSUE=42 GITHUB_OUTPUT="$BATS_TEST_TMPDIR/output"
  : >"$GITHUB_OUTPUT"
}

gate() { "$PIPELINE_DIR/gate-issue-type.sh"; }

@test "accepts an issue whose type is in the list — no edit, no comment" {
  export STUB_ISSUE_LABELS="type:coding-task,status:refined"
  export ACCEPTED="type:coding-task,type:bug,type:spike" REMOVE_STATUS="status:refined" REJECT_COMMENT="nope"
  run gate
  [ "$status" -eq 0 ]
  grep -q 'skip=false' "$GITHUB_OUTPUT"
  ! grep -q 'gh issue edit' "$STUB_LOG"
  ! grep -q 'gh issue comment' "$STUB_LOG"
}

@test "accepts on a match anywhere in the accepted list" {
  export STUB_ISSUE_LABELS="type:spike,status:refined"
  export ACCEPTED="type:coding-task,type:bug,type:spike" REMOVE_STATUS="status:refined" REJECT_COMMENT="nope"
  run gate
  [ "$status" -eq 0 ]
  grep -q 'skip=false' "$GITHUB_OUTPUT"
}

@test "rejects an epic — parks it, comments, signals skip" {
  export STUB_ISSUE_LABELS="type:epic,status:refined"
  export ACCEPTED="type:coding-task,type:bug,type:spike" REMOVE_STATUS="status:refined" \
    REJECT_COMMENT="Epics aren't sized directly."
  run gate
  [ "$status" -eq 0 ]
  grep -q 'skip=true' "$GITHUB_OUTPUT"
  grep -q 'gh issue edit 42 --repo owner/repo --add-label status:needs-attention --remove-label status:refined' "$STUB_LOG"
  grep -q "gh issue comment 42 .* Epics aren't sized directly." "$STUB_LOG"
}

@test "coder gate drops status:ready when it rejects a spike" {
  export STUB_ISSUE_LABELS="type:spike,status:ready"
  export ACCEPTED="type:coding-task,type:bug" REMOVE_STATUS="status:ready" REJECT_COMMENT="not implementable"
  run gate
  [ "$status" -eq 0 ]
  grep -q 'skip=true' "$GITHUB_OUTPUT"
  grep -q 'gh issue edit 42 --repo owner/repo --add-label status:needs-attention --remove-label status:ready' "$STUB_LOG"
}
