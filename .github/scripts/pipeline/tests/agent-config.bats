setup() {
  load helpers
  setup_stubs
  CONFIG="$BATS_TEST_TMPDIR/interns.yml"
  export INTERNS_CONFIG="$CONFIG"
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
  export INTERNS_CONFIG="$BATS_TEST_TMPDIR/none.yml"
  run "$PIPELINE_DIR/agent-config.sh" reviewer
  [ "$status" -eq 0 ]
  [ "$(out model)" = "claude-sonnet-5" ]
  [ "$(out max_turns)" = "40" ]
}

@test "refiner defaults to claude-sonnet-5 for its investigation pass" {
  export INTERNS_CONFIG="$BATS_TEST_TMPDIR/none.yml"
  run "$PIPELINE_DIR/agent-config.sh" refiner
  [ "$status" -eq 0 ]
  [ "$(out model)" = "claude-sonnet-5" ]
}

@test "wiki is disabled by default" {
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$status" -eq 0 ]
  [ "$(out wiki_enabled)" = "false" ]
  [ "$(out wiki_repo)" = "" ]
}

@test "wiki.enabled surfaces wiki.url" {
  printf 'wiki: { enabled: true, url: acme/widgets.wiki }\n' >>"$CONFIG"
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$status" -eq 0 ]
  [ "$(out wiki_enabled)" = "true" ]
  [ "$(out wiki_repo)" = "acme/widgets.wiki" ]
}

@test "rejects wiki.enabled without a url" {
  printf 'wiki: { enabled: true }\n' >>"$CONFIG"
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$status" -ne 0 ]
  [[ "$output" == *"wiki.enabled is true but wiki.url is unset"* ]]
}

@test "rejects an unknown wiki key" {
  printf 'wiki: { enabled: false, comment: nope }\n' >>"$CONFIG"
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$status" -ne 0 ]
  [[ "$output" == *"unknown key 'wiki.comment'"* ]]
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

@test "tolerates the installer's allow_agent_push_to_default_branch knob" {
  echo "allow_agent_push_to_default_branch: true" >>"$CONFIG"
  run "$PIPELINE_DIR/agent-config.sh" coder
  [ "$status" -eq 0 ]
  [ "$(out max_turns)" = "60" ]
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
