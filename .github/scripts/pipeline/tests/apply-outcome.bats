setup() {
  load helpers
  setup_stubs
  export ISSUE=34
  MARKER="$BATS_TEST_TMPDIR/outcome"
  COMMENT="$BATS_TEST_TMPDIR/comment.md"
}

marker() { printf '%s\n' "$1" >"$MARKER"; }
write_scores() {
  printf '%s\n' \
    "BLAST RADIUS: Low — isolated" \
    "TOUCH: Mid — a couple files" \
    "HUMAN INVOLVEMENT: Low — none" \
    "REVIEW OVERHEAD: Mid — one pass" >"$COMMENT"
}

@test "refinement/refined swaps needs-refinement -> refined" {
  marker refined
  run "$PIPELINE_DIR/apply-outcome.sh" refinement "$MARKER"
  [ "$status" -eq 0 ]
  grep -q 'gh issue edit 34 --repo owner/repo --remove-label status:needs-refinement --add-label status:refined' "$STUB_LOG"
  grep -q '^outcome=refined$' "$GITHUB_OUTPUT"
}

@test "refinement/needs-attention swaps needs-refinement -> needs-attention" {
  marker needs-attention
  run "$PIPELINE_DIR/apply-outcome.sh" refinement "$MARKER"
  [ "$status" -eq 0 ]
  grep -q 'gh issue edit 34 --repo owner/repo --remove-label status:needs-refinement --add-label status:needs-attention' "$STUB_LOG"
}

@test "estimation/estimated rolls the scores and applies size + status" {
  marker estimated
  write_scores
  run "$PIPELINE_DIR/apply-outcome.sh" estimation "$MARKER" "$COMMENT"
  [ "$status" -eq 0 ]
  grep -q 'gh issue edit 34 --repo owner/repo --remove-label status:refined --add-label status:estimated --add-label size:S' "$STUB_LOG"
}

@test "estimation/needs-attention swaps refined -> needs-attention" {
  marker needs-attention
  run "$PIPELINE_DIR/apply-outcome.sh" estimation "$MARKER" "$COMMENT"
  [ "$status" -eq 0 ]
  grep -q 'gh issue edit 34 --repo owner/repo --remove-label status:refined --add-label status:needs-attention' "$STUB_LOG"
}

@test "a missing marker fails without touching labels" {
  run "$PIPELINE_DIR/apply-outcome.sh" refinement "$MARKER"
  [ "$status" -eq 1 ]
  ! grep -q 'gh issue edit' "$STUB_LOG"
}

@test "an unrecognised marker word fails without touching labels" {
  marker done
  run "$PIPELINE_DIR/apply-outcome.sh" refinement "$MARKER"
  [ "$status" -eq 1 ]
  ! grep -q 'gh issue edit' "$STUB_LOG"
}

@test "estimation/estimated with a missing score fails without touching labels" {
  marker estimated
  printf '%s\n' "BLAST RADIUS: Low — isolated" "TOUCH: Low — one file" >"$COMMENT"
  run "$PIPELINE_DIR/apply-outcome.sh" estimation "$MARKER" "$COMMENT"
  [ "$status" -eq 1 ]
  ! grep -q 'gh issue edit' "$STUB_LOG"
}
