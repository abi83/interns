setup() {
  load helpers
  setup_stubs
  export GITHUB_STEP_SUMMARY="$BATS_TEST_TMPDIR/summary.md"
  : >"$GITHUB_STEP_SUMMARY"
  EXEC="$BATS_TEST_TMPDIR/exec.json"
}

summary() { cat "$GITHUB_STEP_SUMMARY"; }

@test "coder: issue, round, PR outcome, files, cost, final message" {
  echo '[{"type":"result","total_cost_usd":0.5,"num_turns":7,"result":"All steps done, opening the PR."}]' >"$EXEC"
  export STUB_ISSUE_TITLE="Add a widget"
  export STUB_PR_FILES=$'src/a.ts\nsrc/b.ts\nsrc/c.ts'
  run "$PIPELINE_DIR/run-summary.sh" Coder "$EXEC" --issue 42 --pr 99 --round initial
  [ "$status" -eq 0 ]
  summary | grep -qF '## Coder run'
  summary | grep -qF '**Issue:** [#42](https://github.com/owner/repo/issues/42) — Add a widget'
  summary | grep -qF '**Round:** Initial implementation'
  summary | grep -qF '**Outcome:** PR opened — [#99](https://github.com/owner/repo/pull/99)'
  summary | grep -qF '**Files changed:** 3'
  summary | grep -qF '**Cost:** $0.5000 · 7 turns'
  summary | grep -qF '> All steps done, opening the PR.'
  ! summary | grep -qi 'checks'
}

@test "coder: a failed diff lookup reads 'unknown', not '0'" {
  echo '[{"type":"result","result":"done"}]' >"$EXEC"
  export STUB_GH_EXIT=1
  run "$PIPELINE_DIR/run-summary.sh" Coder "$EXEC" --issue 42 --pr 99 --round initial
  [ "$status" -eq 0 ]
  summary | grep -qF '**Files changed:** unknown'
}

@test "coder: no PR opened surfaces a blocked outcome without the log" {
  echo '[{"type":"result","result":"Could not push the branch: missing workflows permission."}]' >"$EXEC"
  run "$PIPELINE_DIR/run-summary.sh" Coder "$EXEC" --issue 42 --round initial
  [ "$status" -eq 0 ]
  summary | grep -qF '**Outcome:** ⚠️ No PR — see the final message below.'
  summary | grep -qF '> Could not push the branch: missing workflows permission.'
  ! summary | grep -q 'Files changed'
}

@test "coder: fix round that pushed a new commit shows PR updated" {
  echo '[{"type":"result"}]' >"$EXEC"
  export STUB_RC_COUNT=2
  export STUB_LAST_SHA="oldsha"
  export STUB_HEAD_SHA="newsha"
  run "$PIPELINE_DIR/run-summary.sh" Coder "$EXEC" --issue 42 --pr 99 --round fix
  [ "$status" -eq 0 ]
  summary | grep -qF '**Round:** Fix round 2'
  summary | grep -qF '**Outcome:** PR updated — [#99](https://github.com/owner/repo/pull/99)'
}

@test "coder: fix round that pushed nothing shows the blocked outcome" {
  echo '[{"type":"result","result":"Could not push: guarded path."}]' >"$EXEC"
  export STUB_RC_COUNT=1
  export STUB_LAST_SHA="samesha"
  export STUB_HEAD_SHA="samesha"
  run "$PIPELINE_DIR/run-summary.sh" Coder "$EXEC" --issue 42 --pr 99 --round fix
  [ "$status" -eq 0 ]
  summary | grep -qF '**Outcome:** ⚠️ No new commit pushed — see the final message below.'
  summary | grep -qF '> Could not push: guarded path.'
}

@test "review: approved verdict" {
  echo '[{"type":"result","total_cost_usd":0.1,"result":"Looks good, approving."}]' >"$EXEC"
  export STUB_PR_TITLE="feat: widget"
  export STUB_LAST_STATE="APPROVED"
  export STUB_RC_COUNT=0
  export STUB_HEAD_SHA="headsha"
  export STUB_LAST_SHA="headsha"
  export REVIEWER_BOT="prepify-reviewer[bot]"
  run "$PIPELINE_DIR/run-summary.sh" Review "$EXEC" --pr 99 --issue 42
  [ "$status" -eq 0 ]
  summary | grep -qF '**PR:** [#99](https://github.com/owner/repo/pull/99) — feat: widget'
  summary | grep -qF '**Round:** initial review'
  summary | grep -qF '**Outcome:** ✅ Approved'
  summary | grep -qF '> Looks good, approving.'
}

@test "review: no verdict submitted" {
  echo '[{"type":"result","result":"Could not use the review tool, posting here."}]' >"$EXEC"
  export STUB_LAST_STATE=""
  export STUB_RC_COUNT=1
  export STUB_HEAD_SHA="headsha"
  export STUB_LAST_SHA=""
  run "$PIPELINE_DIR/run-summary.sh" Review "$EXEC" --pr 99
  [ "$status" -eq 0 ]
  summary | grep -qF '**Round:** re-review (after 1 changes-requested)'
  summary | grep -qF '**Outcome:** ⚠️ No verdict submitted — see the final message below.'
}

@test "review: a PR's first-ever review requesting changes is 'initial', not 're-review'" {
  echo '[{"type":"result","result":"Requesting changes."}]' >"$EXEC"
  export REVIEWER_BOT="prepify-reviewer[bot]"
  export STUB_HEAD_SHA="head1"
  export STUB_REVIEWS='[{"user":{"login":"prepify-reviewer[bot]"},"state":"CHANGES_REQUESTED","commit_id":"head1"}]'
  run "$PIPELINE_DIR/run-summary.sh" Review "$EXEC" --pr 99
  [ "$status" -eq 0 ]
  summary | grep -qF '**Round:** initial review'
  summary | grep -qF '**Outcome:** 🔴 Changes requested'
}

@test "review: a genuine re-review counts only prior-commit changes-requested" {
  echo '[{"type":"result","result":"Still not there."}]' >"$EXEC"
  export REVIEWER_BOT="prepify-reviewer[bot]"
  export STUB_HEAD_SHA="head2"
  export STUB_REVIEWS='[{"user":{"login":"prepify-reviewer[bot]"},"state":"CHANGES_REQUESTED","commit_id":"head1"},{"user":{"login":"prepify-reviewer[bot]"},"state":"CHANGES_REQUESTED","commit_id":"head2"}]'
  run "$PIPELINE_DIR/run-summary.sh" Review "$EXEC" --pr 99
  [ "$status" -eq 0 ]
  summary | grep -qF '**Round:** re-review (after 1 changes-requested)'
  summary | grep -qF '**Outcome:** 🔴 Changes requested'
}

@test "review: a stale verdict against an old commit is not counted as this run's" {
  echo '[{"type":"result","result":"Stopped early."}]' >"$EXEC"
  export STUB_LAST_STATE="CHANGES_REQUESTED"
  export STUB_RC_COUNT=1
  export STUB_HEAD_SHA="newsha"
  export STUB_LAST_SHA="oldsha"
  run "$PIPELINE_DIR/run-summary.sh" Review "$EXEC" --pr 99
  [ "$status" -eq 0 ]
  summary | grep -qF '**Outcome:** ⚠️ No verdict submitted — see the final message below.'
}

@test "refinement: body refined" {
  echo '[{"type":"result","total_cost_usd":0.02,"result":"Rewrote the body."}]' >"$EXEC"
  export STUB_ISSUE_TITLE="Vague idea"
  export STUB_ISSUE_LABELS="type:coding-task,status:refined"
  run "$PIPELINE_DIR/run-summary.sh" Refinement "$EXEC" --issue 7
  [ "$status" -eq 0 ]
  summary | grep -qF '## Refinement run'
  summary | grep -qF '**Outcome:** Body refined'
}

@test "refinement: stopped for clarification" {
  echo '[{"type":"result","result":"Need to know which API."}]' >"$EXEC"
  export STUB_ISSUE_LABELS="status:needs-attention"
  run "$PIPELINE_DIR/run-summary.sh" Refinement "$EXEC" --issue 7
  summary | grep -qF '**Outcome:** ⚠️ Stopped for clarification — see the final message below.'
}

@test "estimation: estimate posted with size label" {
  echo '[{"type":"result","total_cost_usd":0.03,"result":"SIZE: M"}]' >"$EXEC"
  export STUB_ISSUE_LABELS="type:coding-task,status:estimated,size:M"
  run "$PIPELINE_DIR/run-summary.sh" Estimation "$EXEC" --issue 7
  [ "$status" -eq 0 ]
  summary | grep -qF '**Outcome:** Estimate posted — `size:M`'
}

@test "missing execution file yields an unknown cost and a placeholder message" {
  run "$PIPELINE_DIR/run-summary.sh" Refinement /no/such/file --issue 7
  [ "$status" -eq 0 ]
  summary | grep -qF '**Cost:** $unknown'
  summary | grep -qF '> _No final message — the run produced no result output._'
}

@test "cost over the warn limit adds a warning line" {
  echo '[{"type":"result","total_cost_usd":2.5,"result":"done"}]' >"$EXEC"
  export STUB_ISSUE_LABELS="status:refined"
  run "$PIPELINE_DIR/run-summary.sh" Refinement "$EXEC" --issue 7 --cost-warn 0.30
  [ "$status" -eq 0 ]
  summary | grep -qF '⚠️ cost $2.5000 over the $0.30 warn limit'
}

@test "cost under the warn limit adds no warning line" {
  echo '[{"type":"result","total_cost_usd":0.10,"result":"done"}]' >"$EXEC"
  export STUB_ISSUE_LABELS="status:refined"
  run "$PIPELINE_DIR/run-summary.sh" Refinement "$EXEC" --issue 7 --cost-warn 0.30
  [ "$status" -eq 0 ]
  ! summary | grep -q 'warn limit'
}

@test "missing execution file reports a timeout" {
  export STUB_ISSUE_LABELS="status:in-progress"
  run "$PIPELINE_DIR/run-summary.sh" Refinement "" --issue 7 --cost-warn 0.30
  [ "$status" -eq 0 ]
  summary | grep -qF 'killed (timed out) before writing results'
}

@test "errors on an unknown phase" {
  echo '[]' >"$EXEC"
  run "$PIPELINE_DIR/run-summary.sh" Bogus "$EXEC" --issue 7
  [ "$status" -eq 1 ]
}
