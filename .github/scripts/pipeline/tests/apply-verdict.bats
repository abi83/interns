setup() {
  load helpers
  setup_stubs
  export REVIEWER_BOT="reviewer[bot]"
  export STUB_HEAD_SHA="headsha"
}

@test "APPROVED clears the pr label and tells the issue" {
  export STUB_REVIEWS='[{"user":{"login":"reviewer[bot]"},"state":"APPROVED","commit_id":"headsha"}]'
  export STUB_PR_LABELS="pr:needs-attention"
  run "$PIPELINE_DIR/apply-verdict.sh" 12 34
  [ "$status" -eq 0 ]
  grep -q 'gh pr edit 12 --repo owner/repo --remove-label pr:needs-attention' "$STUB_LOG"
  grep -q 'gh issue comment 34 .* Reviewer approved \[PR #12\](https://github.com/owner/repo/pull/12) — awaiting owner merge' "$STUB_LOG"
}

@test "first CHANGES_REQUESTED with a linked issue dispatches a fix round" {
  export STUB_REVIEWS='[{"user":{"login":"reviewer[bot]"},"state":"CHANGES_REQUESTED","commit_id":"headsha"}]'
  export STUB_PR_LABELS="pr:in-review"
  run "$PIPELINE_DIR/apply-verdict.sh" 12 34
  grep -q 'gh pr edit 12 --repo owner/repo --add-label pr:coding --remove-label pr:in-review' "$STUB_LOG"
  grep -q 'gh workflow run code-pipeline.yml --repo owner/repo --field phase=coder --field issue_number=34 --field fix_round=true' "$STUB_LOG"
}

@test "second CHANGES_REQUESTED escalates and does not dispatch" {
  export STUB_REVIEWS='[{"user":{"login":"reviewer[bot]"},"state":"CHANGES_REQUESTED","commit_id":"oldsha"},{"user":{"login":"reviewer[bot]"},"state":"CHANGES_REQUESTED","commit_id":"headsha"}]'
  export STUB_PR_LABELS="pr:in-review"
  run "$PIPELINE_DIR/apply-verdict.sh" 12 34
  grep -q "didn't converge. Escalating to a human" "$STUB_LOG"
  grep -q 'gh pr edit 12 --repo owner/repo --add-label pr:needs-attention --remove-label pr:in-review' "$STUB_LOG"
  ! grep -q 'gh workflow run' "$STUB_LOG"
}

@test "CHANGES_REQUESTED with no linked issue can't dispatch" {
  export STUB_REVIEWS='[{"user":{"login":"reviewer[bot]"},"state":"CHANGES_REQUESTED","commit_id":"headsha"}]'
  run "$PIPELINE_DIR/apply-verdict.sh" 12 ""
  grep -q "no linked issue" "$STUB_LOG"
  ! grep -q 'gh workflow run' "$STUB_LOG"
}

@test "an unrecognized verdict flags for a human" {
  export STUB_REVIEWS='[{"user":{"login":"reviewer[bot]"},"state":"COMMENTED","commit_id":"headsha"}]'
  export STUB_PR_LABELS="pr:in-review"
  run "$PIPELINE_DIR/apply-verdict.sh" 12 34
  grep -q "without submitting a recognized verdict" "$STUB_LOG"
  grep -q 'gh pr edit 12 --repo owner/repo --add-label pr:needs-attention --remove-label pr:in-review' "$STUB_LOG"
}

@test "a stale review against an earlier commit flags for a human" {
  export STUB_REVIEWS='[{"user":{"login":"reviewer[bot]"},"state":"APPROVED","commit_id":"oldsha"}]'
  export STUB_PR_LABELS="pr:in-review"
  run "$PIPELINE_DIR/apply-verdict.sh" 12 34
  grep -q "without submitting a recognized verdict" "$STUB_LOG"
}
