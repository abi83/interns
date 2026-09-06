setup() {
  load helpers
  PIPELINE_DIR="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)"
  BUILTIN="$BATS_TEST_TMPDIR/builtin"
  CONSUMER="$BATS_TEST_TMPDIR/consumer"
  mkdir -p "$BUILTIN" "$CONSUMER"
  export GITHUB_OUTPUT="$BATS_TEST_TMPDIR/output"
  : >"$GITHUB_OUTPUT"

  printf -- '---\nlabels: type:coding-task\n---\n## Value\n<!-- why -->\n## Scope\n' >"$BUILTIN/coding-task.md"
  printf -- '---\nlabels: type:bug\n---\n## Description\n## Impact\n' >"$BUILTIN/bug.md"
  printf -- '## Question to Answer\n' >"$BUILTIN/spike.md"
}

resolve() {
  BUILTIN_DIR="$BUILTIN" CONSUMER_DIR="$CONSUMER" TYPES="coding-task bug spike" \
    "$PIPELINE_DIR/resolve-issue-template.sh"
}

@test "emits a heading-only block per type, frontmatter and comments gone" {
  run resolve
  [ "$status" -eq 0 ]
  skel="$(sed -n '/^skeleton<<EOF_SKELETON$/,/^EOF_SKELETON$/p' "$GITHUB_OUTPUT")"
  [[ "$skel" == *"type:coding-task"$'\n'"## Value"$'\n'"## Scope"* ]]
  [[ "$skel" == *"type:bug"$'\n'"## Description"$'\n'"## Impact"* ]]
  [[ "$skel" != *"---"* ]]
  [[ "$skel" != *"<!--"* ]]
}

@test "consumer override wins when present" {
  printf -- '---\nlabels: type:bug\n---\n## Custom\n## Fields\n' >"$CONSUMER/bug.md"
  run resolve
  [ "$status" -eq 0 ]
  grep -q '## Custom' "$GITHUB_OUTPUT"
  ! grep -q '## Description' "$GITHUB_OUTPUT"
}

@test "fails when a type has no template anywhere" {
  rm "$BUILTIN/spike.md"
  run resolve
  [ "$status" -ne 0 ]
  [[ "$output" == *"no template for 'spike'"* ]]
}
