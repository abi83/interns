setup() {
  load helpers
  setup_stubs
}

derive() { "$PIPELINE_DIR/derive-code-hints.sh" 42; }

@test "type:coding-task maps to feat: and a feat/ branch" {
  export STUB_ISSUE_LABELS="type:coding-task,status:ready"
  export STUB_ISSUE_TITLE="Pass the coder deterministic commit-type hints"
  run derive
  [ "$status" -eq 0 ]
  grep -q 'commit_type_hint=feat:' "$GITHUB_OUTPUT"
  grep -q 'branch=feat/issue-42-pass-the-coder-deterministic-commit-typ' "$GITHUB_OUTPUT"
}

@test "type:bug maps to fix: and a fix/ branch" {
  export STUB_ISSUE_LABELS="type:bug,status:ready"
  export STUB_ISSUE_TITLE="Crash on empty input"
  run derive
  [ "$status" -eq 0 ]
  grep -q 'commit_type_hint=fix:' "$GITHUB_OUTPUT"
  grep -q 'branch=fix/issue-42-crash-on-empty-input' "$GITHUB_OUTPUT"
}

@test "slug strips punctuation, collapses separators, trims trailing dashes" {
  export STUB_ISSUE_LABELS="type:coding-task"
  export STUB_ISSUE_TITLE="  Refine: the (refiner) -- stop!  "
  run derive
  [ "$status" -eq 0 ]
  grep -q 'branch=feat/issue-42-refine-the-refiner-stop' "$GITHUB_OUTPUT"
}

@test "fails when no implementable type label is present" {
  export STUB_ISSUE_LABELS="type:spike"
  export STUB_ISSUE_TITLE="Investigate something"
  run derive
  [ "$status" -ne 0 ]
  [[ "$output" == *"neither type:bug nor type:coding-task"* ]]
}
