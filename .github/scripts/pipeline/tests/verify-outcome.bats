setup() {
  load helpers
  setup_stubs
}

@test "no-op when the issue already carries an expected label" {
  export STUB_ISSUE_LABELS="type:bug,status:refined"
  run "$PIPELINE_DIR/verify-outcome.sh" Refinement 3 status:refined status:needs-attention
  [ "$status" -eq 0 ]
  ! grep -q 'gh issue comment' "$STUB_LOG"
  ! grep -q 'gh issue edit' "$STUB_LOG"
}

@test "two expected labels render as 'a or b'" {
  export STUB_ISSUE_LABELS="status:needs-refinement"
  run "$PIPELINE_DIR/verify-outcome.sh" Refinement 3 status:refined status:needs-attention
  grep -q 'gh issue comment 3 .* Refinement run completed without leaving the issue in `status:refined` or `status:needs-attention` — likely stopped partway through. See the run: https://github.com/owner/repo/actions/runs/42' "$STUB_LOG"
}

@test "three expected labels use an Oxford comma" {
  export STUB_ISSUE_LABELS="status:estimated-wrong"
  run "$PIPELINE_DIR/verify-outcome.sh" Estimation 3 status:estimated status:ready status:needs-attention
  grep -q '`status:estimated`, `status:ready`, or `status:needs-attention`' "$STUB_LOG"
}

@test "flags the issue for a human when no expected label is present" {
  export STUB_ISSUE_LABELS="status:needs-refinement"
  run "$PIPELINE_DIR/verify-outcome.sh" Refinement 3 status:refined status:needs-attention
  grep -q 'gh issue edit 3 --repo owner/repo --add-label status:needs-attention' "$STUB_LOG"
}
