setup() {
  load helpers
  setup_stubs
  source "$PIPELINE_DIR/lib.sh"
}

@test "run_url builds the workflow run URL from the env" {
  run run_url
  [ "$status" -eq 0 ]
  [ "$output" = "https://github.com/owner/repo/actions/runs/42" ]
}

@test "format_cost rounds to 4 decimals" {
  run format_cost 0.123456
  [ "$output" = "0.1235" ]
}

@test "format_cost returns unknown for an empty value" {
  run format_cost ""
  [ "$output" = "unknown" ]
}

# The label state machine itself (which labels to add/remove for a given
# transition, the best-effort swallow, the "don't remove an absent label"
# guard) is unit-tested against a mocked `gh` in pipeline/tests/test_labels.py.
# These just check the bash wrappers wire lib.sh's args through to the real
# `python -m pipeline.labels` and back out to `gh` correctly.

@test "issue_labels_csv reads labels through pipeline.labels" {
  export STUB_ISSUE_LABELS="type:bug,status:ready"
  run issue_labels_csv 7
  [ "$status" -eq 0 ]
  [ "$output" = "type:bug,status:ready" ]
  grep -qF -- "gh issue view 7 --repo owner/repo --json labels" "$STUB_LOG"
}

@test "pr_labels_csv reads labels through pipeline.labels" {
  export STUB_PR_LABELS="pr:in-review"
  run pr_labels_csv 3
  [ "$output" = "pr:in-review" ]
  grep -qF -- "gh pr view 3 --repo owner/repo --json labels" "$STUB_LOG"
}

@test "set_issue_status adds the target and removes only present lifecycle labels" {
  export STUB_ISSUE_LABELS="type:bug,status:in-progress"
  run set_issue_status 7 status:needs-attention
  [ "$status" -eq 0 ]
  grep -qF -- "gh issue edit 7 --repo owner/repo --add-label status:needs-attention --remove-label status:in-progress" "$STUB_LOG"
  ! grep -qF -- "--remove-label status:ready" "$STUB_LOG"
}

@test "edit_issue_labels only removes a label that's actually present" {
  export STUB_ISSUE_LABELS="status:refined"
  run edit_issue_labels 7 --add status:needs-attention --remove status:ready
  grep -qF -- "gh issue edit 7 --repo owner/repo --add-label status:needs-attention" "$STUB_LOG"
  ! grep -qF -- "--remove-label" "$STUB_LOG"
}

@test "set_pr_pipeline_label swaps to the target label" {
  export STUB_PR_LABELS="pr:in-review"
  run set_pr_pipeline_label 3 pr:coding
  grep -qF -- "gh pr edit 3 --repo owner/repo --add-label pr:coding --remove-label pr:in-review" "$STUB_LOG"
}

@test "set_pr_pipeline_label with no target clears the present pr label" {
  export STUB_PR_LABELS="pr:in-review,size:S"
  run set_pr_pipeline_label 3
  grep -qF -- "gh pr edit 3 --repo owner/repo --remove-label pr:in-review" "$STUB_LOG"
}

@test "set_pr_pipeline_label is a no-op when nothing changes" {
  export STUB_PR_LABELS="size:S"
  run set_pr_pipeline_label 3
  [ "$status" -eq 0 ]
  ! grep -q "gh pr edit" "$STUB_LOG"
}

@test "escalate_pr swaps an agent label for pr:needs-attention" {
  export STUB_PR_LABELS="pr:in-review"
  run escalate_pr 3
  grep -qF -- "gh pr edit 3 --repo owner/repo --add-label pr:needs-attention --remove-label pr:in-review" "$STUB_LOG"
}
