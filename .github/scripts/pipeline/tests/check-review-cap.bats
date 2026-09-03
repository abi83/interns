setup() {
  load helpers
  setup_stubs
  export REVIEWER_BOT="reviewer[bot]"
  export MAX_AUTOMATIC_REVIEWS_PER_PR=5
}

# A reviews payload with $1 reviews by the reviewer bot plus one human review.
reviews_fixture() {
  local n="$1" out='[{"user":{"login":"somedev"},"state":"COMMENTED"}]'
  for ((i = 0; i < n; i++)); do
    out=$(jq -c '. + [{"user":{"login":"reviewer[bot]"},"state":"CHANGES_REQUESTED"}]' <<<"$out")
  done
  printf '%s' "$out"
}

@test "under the cap: capped=false, no comment, no label edit" {
  export STUB_REVIEWS="$(reviews_fixture 4)"
  run "$PIPELINE_DIR/check-review-cap.sh" 12
  [ "$status" -eq 0 ]
  grep -q '^capped=false$' "$GITHUB_OUTPUT"
  ! grep -q 'gh pr comment' "$STUB_LOG"
  ! grep -q 'gh pr edit' "$STUB_LOG"
}

@test "at the cap: capped=true, comments, marks pr:needs-attention" {
  export STUB_REVIEWS="$(reviews_fixture 5)" STUB_PR_LABELS="pr:in-review"
  run "$PIPELINE_DIR/check-review-cap.sh" 12
  [ "$status" -eq 0 ]
  grep -q '^capped=true$' "$GITHUB_OUTPUT"
  grep -q 'gh pr comment 12 .* Automatic review limit (5) reached — further review is manual' "$STUB_LOG"
  grep -q 'gh pr edit 12 --repo owner/repo --remove-label pr:in-review --add-label pr:needs-attention' "$STUB_LOG"
}

@test "over the cap also caps" {
  export STUB_REVIEWS="$(reviews_fixture 7)"
  run "$PIPELINE_DIR/check-review-cap.sh" 12
  [ "$status" -eq 0 ]
  grep -q '^capped=true$' "$GITHUB_OUTPUT"
}

@test "cap is configurable via MAX_AUTOMATIC_REVIEWS_PER_PR" {
  export MAX_AUTOMATIC_REVIEWS_PER_PR=2 STUB_REVIEWS="$(reviews_fixture 2)"
  run "$PIPELINE_DIR/check-review-cap.sh" 12
  grep -q '^capped=true$' "$GITHUB_OUTPUT"
}
