setup() {
  load helpers
  setup_stubs
}

@test "standard failure: needs-attention on the issue plus a comment" {
  export STUB_ISSUE_LABELS="status:in-progress"
  run "$PIPELINE_DIR/flag-failure.sh" --noun implementation --issue 9
  [ "$status" -eq 0 ]
  grep -q 'gh issue edit 9 --repo owner/repo --add-label status:needs-attention --remove-label status:in-progress' "$STUB_LOG"
  grep -q 'gh issue comment 9 .* Automated implementation failed. See the run: https://github.com/owner/repo/actions/runs/42' "$STUB_LOG"
}

@test "review failure comments on the PR, not the issue" {
  run "$PIPELINE_DIR/flag-failure.sh" --noun review --pr 4 --issue 9
  grep -q 'gh pr comment 4 .* Automated review failed' "$STUB_LOG"
  ! grep -q 'gh issue comment' "$STUB_LOG"
}

@test "fix-round failure posts the re-dispatch command on the issue" {
  run "$PIPELINE_DIR/flag-failure.sh" --noun implementation --issue 9 --pr 4 --fix-round
  grep -q 'gh issue comment 9 .*gh workflow run code-pipeline.yml -f phase=coder -f issue_number=9 -f fix_round=true' "$STUB_LOG"
  ! grep -q 'Automated implementation failed' "$STUB_LOG"
}

@test "an empty --issue is treated as absent" {
  run "$PIPELINE_DIR/flag-failure.sh" --noun review --pr 4 --issue ""
  [ "$status" -eq 0 ]
  ! grep -q 'gh issue' "$STUB_LOG"
}

@test "rejects an unknown argument" {
  run "$PIPELINE_DIR/flag-failure.sh" --noun review --wat
  [ "$status" -eq 1 ]
}
