setup() {
  load helpers
  setup_stubs
  export CHECK_POLL_SECONDS=0
  export CHECK_SETTLE_SECONDS=0
}

# A check that belongs to some other workflow run.
chk() { printf '{"name":"%s","bucket":"%s","link":"https://github.com/owner/repo/actions/runs/99/job/1"}' "$1" "$2"; }

@test "workflow_dispatch skips the gate" {
  export GITHUB_EVENT_NAME=workflow_dispatch
  run "$PIPELINE_DIR/wait-for-checks.sh" ""
  [ "$status" -eq 0 ]
  grep -qx 'ok=true' "$GITHUB_OUTPUT"
}

@test "every check green -> ok=true" {
  export STUB_PR_CHECKS="[$(chk test pass),$(chk build pass),$(chk lint pass),$(chk coverage skipping)]"
  run "$PIPELINE_DIR/wait-for-checks.sh" 5
  [ "$status" -eq 0 ]
  grep -qx 'ok=true' "$GITHUB_OUTPUT"
}

@test "one red among several green -> ok=false with a reason naming it" {
  export STUB_PR_CHECKS="[$(chk test pass),$(chk build pass),$(chk lint fail),$(chk typecheck pass)]"
  run "$PIPELINE_DIR/wait-for-checks.sh" 5
  [ "$status" -eq 0 ]
  grep -qx 'ok=false' "$GITHUB_OUTPUT"
  grep -q 'reason=red checks: lint=fail' "$GITHUB_OUTPUT"
}

@test "a cancelled check counts as red" {
  export STUB_PR_CHECKS="[$(chk test pass),$(chk build cancel)]"
  run "$PIPELINE_DIR/wait-for-checks.sh" 5
  grep -qx 'ok=false' "$GITHUB_OUTPUT"
  grep -q 'build=cancel' "$GITHUB_OUTPUT"
}

@test "a pending check that later passes -> ok=true" {
  cat >"$BATS_TEST_TMPDIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
n="$BATS_TEST_TMPDIR/n"; c=$(( $(cat "$n" 2>/dev/null || echo 0) + 1 )); echo "$c" >"$n"
if [ "$c" -lt 2 ]; then
  echo '[{"name":"test","bucket":"pending","link":"https://github.com/owner/repo/actions/runs/99/job/1"}]'
else
  echo '[{"name":"test","bucket":"pass","link":"https://github.com/owner/repo/actions/runs/99/job/1"}]'
fi
EOF
  chmod +x "$BATS_TEST_TMPDIR/bin/gh"
  run "$PIPELINE_DIR/wait-for-checks.sh" 5
  [ "$status" -eq 0 ]
  grep -qx 'ok=true' "$GITHUB_OUTPUT"
}

@test "the reviewer's own run is excluded from the set it waits on" {
  # Only check present belongs to this run ($GITHUB_RUN_ID=42) and is pending;
  # with a zero settle window that must resolve to "no checks -> ok=true", not
  # a timeout.
  export STUB_PR_CHECKS='[{"name":"pipeline / reviewer","bucket":"pending","link":"https://github.com/owner/repo/actions/runs/42/job/7"}]'
  run "$PIPELINE_DIR/wait-for-checks.sh" 5
  [ "$status" -eq 0 ]
  grep -qx 'ok=true' "$GITHUB_OUTPUT"
}

@test "checks.ignore in the config drops an advisory check" {
  export INTERNS_CONFIG="$BATS_TEST_TMPDIR/interns.yml"
  cat >"$INTERNS_CONFIG" <<'EOF'
checks:
  ignore:
    - preview-deploy
EOF
  export STUB_PR_CHECKS="[$(chk test pass),$(chk preview-deploy fail)]"
  run "$PIPELINE_DIR/wait-for-checks.sh" 5
  [ "$status" -eq 0 ]
  grep -qx 'ok=true' "$GITHUB_OUTPUT"
}

@test "times out when a check never resolves" {
  export STUB_PR_CHECKS="[$(chk test pending),$(chk build pass)]"
  export CHECK_TIMEOUT_SECONDS=0
  run "$PIPELINE_DIR/wait-for-checks.sh" 5
  [ "$status" -eq 0 ]
  grep -qx 'ok=false' "$GITHUB_OUTPUT"
  grep -q 'reason=timed out waiting for checks to finish: test' "$GITHUB_OUTPUT"
}

@test "no checks at all -> ok=true after the settle window" {
  export STUB_PR_CHECKS='[]'
  run "$PIPELINE_DIR/wait-for-checks.sh" 5
  [ "$status" -eq 0 ]
  grep -qx 'ok=true' "$GITHUB_OUTPUT"
}
