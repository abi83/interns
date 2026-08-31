setup() {
  load helpers
  setup_stubs
}

@test "comments on the issue with the parsed cost" {
  echo '[{"type":"result","total_cost_usd":0.42}]' >"$BATS_TEST_TMPDIR/exec.json"
  run "$PIPELINE_DIR/report-run.sh" Coder "$BATS_TEST_TMPDIR/exec.json" 55
  [ "$status" -eq 0 ]
  grep -q 'gh issue comment 55 --repo owner/repo --body Coder \[pipeline run\](https://github.com/owner/repo/actions/runs/42) — cost: \$0.4200' "$STUB_LOG"
}

@test "falls back to the PR only when the issue number is empty" {
  echo '[{"type":"result","total_cost_usd":1}]' >"$BATS_TEST_TMPDIR/exec.json"
  run "$PIPELINE_DIR/report-run.sh" Review "$BATS_TEST_TMPDIR/exec.json" "" 88
  [ "$status" -eq 0 ]
  grep -q 'gh pr comment 88 ' "$STUB_LOG"
  ! grep -q 'gh issue comment' "$STUB_LOG"
}

@test "missing execution file yields an unknown cost" {
  run "$PIPELINE_DIR/report-run.sh" Coder /no/such/file 55
  [ "$status" -eq 0 ]
  grep -q 'cost: \$unknown' "$STUB_LOG"
}

@test "errors when given neither an issue nor a PR" {
  echo '[]' >"$BATS_TEST_TMPDIR/exec.json"
  run "$PIPELINE_DIR/report-run.sh" Coder "$BATS_TEST_TMPDIR/exec.json" "" ""
  [ "$status" -eq 1 ]
}
