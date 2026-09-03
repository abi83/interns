setup() {
  load helpers
  setup_stubs
  export GH_TOKEN=x GITHUB_REPOSITORY=owner/repo GITHUB_RUN_ID=42
}

@test "rejects a file that is not a JSON object" {
  echo 'not json' >"$BATS_TEST_TMPDIR/bad.json"
  run "$PIPELINE_DIR/append-metrics.sh" "$BATS_TEST_TMPDIR/bad.json"
  [ "$status" -ne 0 ]
  # nothing pushed
  ! grep -q 'git .*push' "$STUB_LOG"
}

@test "rejects a missing file" {
  run "$PIPELINE_DIR/append-metrics.sh" /no/such/record.json
  [ "$status" -ne 0 ]
}

@test "errors with no arguments" {
  run "$PIPELINE_DIR/append-metrics.sh"
  [ "$status" -ne 0 ]
}

@test "valid records drive a fetch + commit + push on the metrics branch" {
  echo '{"schema_version":1,"job":"coder"}' >"$BATS_TEST_TMPDIR/rec.json"
  run "$PIPELINE_DIR/append-metrics.sh" "$BATS_TEST_TMPDIR/rec.json"
  [ "$status" -eq 0 ]
  grep -q 'git -C .* fetch -q --depth=1 origin metrics' "$STUB_LOG"
  grep -q 'git -C .* commit -q -m chore(metrics): append records from run 42' "$STUB_LOG"
  grep -q 'git -C .* push -q origin HEAD:metrics' "$STUB_LOG"
}
