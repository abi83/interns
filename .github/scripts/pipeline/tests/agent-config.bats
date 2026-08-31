setup() {
  load helpers
  setup_stubs
  CONFIG="$BATS_TEST_TMPDIR/agent-pipeline.yml"
  export AGENT_PIPELINE_CONFIG="$CONFIG"
  cat >"$CONFIG" <<'EOF'
defaults:
  model: claude-sonnet-5
  max_turns: 40
  timeout_minutes: 30
  max_output_tokens: 32000
  cost_warn_usd: 1.50
agents:
  refiner: { model: claude-haiku-4-5-20251001, max_turns: 15 }
  coder:   { max_turns: 60, timeout_minutes: 45 }
EOF
}

out() { grep "^$1=" "$GITHUB_OUTPUT" | cut -d= -f2-; }

@test "agent override wins over defaults" {
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$status" -eq 0 ]
  [ "$(out max_turns)" = "60" ]
  [ "$(out timeout_minutes)" = "45" ]
}

@test "unset agent key falls back to defaults" {
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$(out model)" = "claude-sonnet-5" ]
  [ "$(out max_output_tokens)" = "32000" ]
}

@test "missing config file falls back to built-in defaults" {
  export AGENT_PIPELINE_CONFIG="$BATS_TEST_TMPDIR/none.yml"
  run "$PIPELINE_DIR/agent-config.sh" reviewer
  [ "$status" -eq 0 ]
  [ "$(out model)" = "claude-sonnet-5" ]
  [ "$(out max_turns)" = "40" ]
}

@test "Actions var is the middle layer between file and built-in" {
  export AGENT_PIPELINE_CONFIG="$BATS_TEST_TMPDIR/none.yml"
  PIPELINE_MODEL=my-model run "$PIPELINE_DIR/agent-config.sh" reviewer
  [ "$(out model)" = "my-model" ]
}

@test "file value beats the Actions var" {
  PIPELINE_MODEL=my-model run "$PIPELINE_DIR/agent-config.sh" refiner
  [ "$(out model)" = "claude-haiku-4-5-20251001" ]
}

@test "rejects an unknown agent argument" {
  run "$PIPELINE_DIR/agent-config.sh" tester
  [ "$status" -ne 0 ]
}

@test "rejects an unknown top-level key" {
  echo "junk: 1" >>"$CONFIG"
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown top-level key 'junk'"* ]]
}

@test "rejects an unknown agent block" {
  printf '  tester: { max_turns: 5 }\n' >>"$CONFIG"
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown agent 'tester'"* ]]
}

@test "rejects an unknown limit key" {
  cat >"$CONFIG" <<'EOF'
defaults: { max_tokens: 100 }
EOF
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown key 'defaults.max_tokens'"* ]]
}

@test "rejects a malformed file" {
  printf 'defaults: [1\n' >"$CONFIG"
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$status" -ne 0 ]
}

@test "rejects max_output_tokens below the floor" {
  cat >"$CONFIG" <<'EOF'
defaults: { max_output_tokens: 8000 }
EOF
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$status" -ne 0 ]
  [[ "$output" == *"safety ceiling"* ]]
}

@test "rejects a non-positive cost_warn_usd" {
  cat >"$CONFIG" <<'EOF'
defaults: { cost_warn_usd: 0 }
EOF
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$status" -ne 0 ]
}
