setup() {
  load helpers
  setup_stubs
  cd "$BATS_TEST_TMPDIR"
}

check() { "$PIPELINE_DIR/check-build-config.sh"; }

@test "no Makefile at all -> not configured" {
  run check
  [ "$status" -eq 0 ]
  grep -q 'configured=false' "$GITHUB_OUTPUT"
}

@test "Makefile still has the stub marker -> not configured" {
  printf 'test:\n\t@echo "INTERNS: not configured -- no tests configured"\n' >Makefile
  run check
  [ "$status" -eq 0 ]
  grep -q 'configured=false' "$GITHUB_OUTPUT"
}

@test "Makefile with the marker gone -> configured" {
  printf 'test:\n\tnpm test\n\nbuild:\n\tnpm run build\n' >Makefile
  run check
  [ "$status" -eq 0 ]
  grep -q 'configured=true' "$GITHUB_OUTPUT"
}
