setup() {
  load helpers
  setup_stubs
  export GITHUB_RUN_ATTEMPT=2

  EXEC="$BATS_TEST_TMPDIR/exec.json"
  cat >"$EXEC" <<'EOF'
[
  {"type":"system","subtype":"init","session_id":"sess-1"},
  {"type":"assistant","isSidechain":false,"message":{"role":"assistant","content":[
    {"type":"text","text":"hi"},
    {"type":"tool_use","name":"Read","input":{}},
    {"type":"tool_use","name":"Bash","input":{}}
  ]}},
  {"type":"assistant","message":{"role":"assistant","content":[
    {"type":"tool_use","name":"Bash","input":{}},
    {"type":"tool_use","name":"Task","input":{}}
  ]}},
  {"type":"assistant","isSidechain":true,"message":{"role":"assistant","content":[
    {"type":"tool_use","name":"Grep","input":{}}
  ]}},
  {"type":"result","subtype":"success","session_id":"sess-1","num_turns":7,
   "duration_ms":812345,"duration_api_ms":431200,"total_cost_usd":0.42,
   "modelUsage":{
     "claude-sonnet-5":{"inputTokens":12000,"outputTokens":48000,"cacheReadInputTokens":980000,"cacheCreationInputTokens":60000,"costUSD":0.4},
     "claude-haiku-4-5":{"inputTokens":300000,"outputTokens":12000,"costUSD":0.02}
   }}
]
EOF
}

@test "emits one line with the core run fields" {
  run "$PIPELINE_DIR/extract-metrics.sh" "$EXEC" --job coder --issue 117 --pr 128
  [ "$status" -eq 0 ]
  [ "$(printf '%s\n' "$output" | wc -l | tr -d ' ')" -eq 1 ]
  echo "$output" | jq -e '
    .schema_version == 1 and .repo == "owner/repo" and .run_id == 42 and
    .run_attempt == 2 and .job == "coder" and .issue == 117 and .pr == 128 and
    .session_id == "sess-1" and .agent_result == "success" and .num_turns == 7 and
    .duration_ms == 812345 and .duration_api_ms == 431200
  '
}

@test "nests per-model usage, sub-agent models included, snake_cased" {
  run "$PIPELINE_DIR/extract-metrics.sh" "$EXEC" --job coder --issue 117
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '
    (.models | keys | sort) == ["claude-haiku-4-5","claude-sonnet-5"] and
    .models["claude-sonnet-5"].cache_read_tokens == 980000 and
    .models["claude-sonnet-5"].cost_usd == 0.4 and
    .models["claude-haiku-4-5"].cache_read_tokens == 0
  '
}

@test "counts main-agent tool_use blocks only, grouped by name" {
  run "$PIPELINE_DIR/extract-metrics.sh" "$EXEC" --job coder
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.tool_calls == {"Read":1,"Bash":2,"Task":1}'
}

@test "empty issue / pr become null" {
  run "$PIPELINE_DIR/extract-metrics.sh" "$EXEC" --job refiner --issue "" --pr ""
  [ "$status" -eq 0 ]
  echo "$output" | jq -e '.issue == null and .pr == null and .job == "refiner"'
}

@test "rejects an unknown job" {
  run "$PIPELINE_DIR/extract-metrics.sh" "$EXEC" --job nope
  [ "$status" -ne 0 ]
}

@test "fails when the execution file has no result event" {
  echo '[{"type":"system"}]' >"$BATS_TEST_TMPDIR/noresult.json"
  run "$PIPELINE_DIR/extract-metrics.sh" "$BATS_TEST_TMPDIR/noresult.json" --job coder
  [ "$status" -ne 0 ]
  [ -z "$output" ] || [[ "$output" != *"{"* ]]
}

@test "fails when the execution file is missing" {
  run "$PIPELINE_DIR/extract-metrics.sh" /no/such/file --job coder
  [ "$status" -ne 0 ]
}
