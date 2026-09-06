setup() {
  load helpers
  setup_stubs
  export ISSUE=34
  COMMENT="$BATS_TEST_TMPDIR/comment.md"
}

write_comment() { printf '%s\n' "$@" >"$COMMENT"; }

@test "rolls the four scores and applies size + status labels" {
  write_comment \
    "BLAST RADIUS: Low — isolated" \
    "TOUCH: Mid — a couple files" \
    "HUMAN INVOLVEMENT: Low — none" \
    "REVIEW OVERHEAD: Mid — one pass"
  run "$PIPELINE_DIR/roll-up-estimate.sh" "$COMMENT"
  [ "$status" -eq 0 ]
  grep -q 'gh issue edit 34 --repo owner/repo --remove-label status:refined --add-label status:estimated --add-label size:S' "$STUB_LOG"
}

@test "label match is case-insensitive and tolerates extra prose" {
  write_comment \
    "blast radius: High — auth" \
    "Touch: High — many modules" \
    "HUMAN INVOLVEMENT: High — manual verification everywhere" \
    "REVIEW OVERHEAD: Mid — a pass or two"
  run "$PIPELINE_DIR/roll-up-estimate.sh" "$COMMENT"
  [ "$status" -eq 0 ]
  grep -q -- '--add-label size:XL' "$STUB_LOG"
}

@test "a missing score fails without touching labels" {
  write_comment \
    "BLAST RADIUS: Low — isolated" \
    "TOUCH: Low — one file"
  run "$PIPELINE_DIR/roll-up-estimate.sh" "$COMMENT"
  [ "$status" -eq 1 ]
  ! grep -q 'gh issue edit' "$STUB_LOG"
}

@test "an unparseable score is rejected by roll-up-size" {
  write_comment \
    "BLAST RADIUS: Medium — hedged" \
    "TOUCH: Low — one file" \
    "HUMAN INVOLVEMENT: Low — none" \
    "REVIEW OVERHEAD: Low — one pass"
  run "$PIPELINE_DIR/roll-up-estimate.sh" "$COMMENT"
  [ "$status" -ne 0 ]
  ! grep -q 'gh issue edit' "$STUB_LOG"
}
