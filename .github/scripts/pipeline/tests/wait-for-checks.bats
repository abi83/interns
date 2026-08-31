setup() {
  load helpers
  setup_stubs
}

@test "workflow_dispatch skips the gate" {
  export GITHUB_EVENT_NAME=workflow_dispatch
  run "$PIPELINE_DIR/wait-for-checks.sh" ""
  [ "$status" -eq 0 ]
  grep -qx 'ok=true' "$GITHUB_OUTPUT"
}

@test "both checks passing -> ok=true" {
  export STUB_PR_CHECKS='[{"name":"test","bucket":"pass"},{"name":"build","bucket":"pass"}]'
  run "$PIPELINE_DIR/wait-for-checks.sh" 5
  [ "$status" -eq 0 ]
  grep -qx 'ok=true' "$GITHUB_OUTPUT"
}

@test "a failing check -> ok=false with a reason" {
  export STUB_PR_CHECKS='[{"name":"test","bucket":"fail"},{"name":"build","bucket":"pass"}]'
  run "$PIPELINE_DIR/wait-for-checks.sh" 5
  [ "$status" -eq 0 ]
  grep -qx 'ok=false' "$GITHUB_OUTPUT"
  grep -qx 'reason=`test`=fail, `build`=pass' "$GITHUB_OUTPUT"
}

@test "times out when a check never resolves" {
  export STUB_PR_CHECKS='[{"name":"test","bucket":"pending"},{"name":"build","bucket":"pending"}]'
  export CHECK_TIMEOUT_SECONDS=0
  run "$PIPELINE_DIR/wait-for-checks.sh" 5
  [ "$status" -eq 0 ]
  grep -qx 'ok=false' "$GITHUB_OUTPUT"
  grep -q 'reason=timed out' "$GITHUB_OUTPUT"
}
