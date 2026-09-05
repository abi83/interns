#!/usr/bin/env bats
#
# Tests for stage-stubs.sh — runs against a throwaway repo tree and a fake
# interns checkout, both under $BATS_TEST_TMPDIR.

setup() {
  SCRIPT="$(cd "$(dirname "$BATS_TEST_FILENAME")/.." && pwd)/stage-stubs.sh"

  INTERNS="$BATS_TEST_TMPDIR/interns"
  mkdir -p "$INTERNS/templates/workflows" "$INTERNS/templates/config" "$INTERNS/templates/issue"
  echo "issue-stub"  > "$INTERNS/templates/workflows/issue-pipeline.yml"
  echo "code-stub"   > "$INTERNS/templates/workflows/code-pipeline.yml"
  echo "config-stub" > "$INTERNS/templates/config/interns.yml"
  echo "bug"         > "$INTERNS/templates/issue/bug.md"
  echo "cfg"         > "$INTERNS/templates/issue/config.yml"

  REPO="$BATS_TEST_TMPDIR/repo"
  mkdir -p "$REPO"
  cd "$REPO"
  export GITHUB_OUTPUT="$BATS_TEST_TMPDIR/gh-output"
  : > "$GITHUB_OUTPUT"
}

changed() { grep -oE 'changed=[01]' "$GITHUB_OUTPUT" | tail -1; }

@test "copies every stub into a bare repo" {
  run "$SCRIPT" "$INTERNS"
  [ "$status" -eq 0 ]
  [ "$(cat "$REPO/.github/workflows/issue-pipeline.yml")" = "issue-stub" ]
  [ "$(cat "$REPO/.github/workflows/code-pipeline.yml")" = "code-stub" ]
  [ "$(cat "$REPO/.github/interns.yml")" = "config-stub" ]
  [ "$(changed)" = "changed=1" ]
}

@test "never overwrites an existing file" {
  mkdir -p "$REPO/.github/workflows"
  echo "MINE" > "$REPO/.github/workflows/issue-pipeline.yml"
  run "$SCRIPT" "$INTERNS"
  [ "$status" -eq 0 ]
  [ "$(cat "$REPO/.github/workflows/issue-pipeline.yml")" = "MINE" ]
  [[ "$output" == *"skip (exists)"* ]]
}

@test "changed=0 when everything is already present" {
  "$SCRIPT" "$INTERNS" >/dev/null
  : > "$GITHUB_OUTPUT"
  run "$SCRIPT" "$INTERNS"
  [ "$status" -eq 0 ]
  [ "$(changed)" = "changed=0" ]
}

@test "issue templates added only when asked and dir absent" {
  run "$SCRIPT" "$INTERNS" true
  [ "$status" -eq 0 ]
  [ "$(cat "$REPO/.github/ISSUE_TEMPLATE/bug.md")" = "bug" ]
}

@test "issue templates skipped when the dir already exists" {
  mkdir -p "$REPO/.github/ISSUE_TEMPLATE"
  run "$SCRIPT" "$INTERNS" true
  [ "$status" -eq 0 ]
  [ ! -e "$REPO/.github/ISSUE_TEMPLATE/bug.md" ]
}

@test "issue templates skipped when not asked" {
  run "$SCRIPT" "$INTERNS" false
  [ "$status" -eq 0 ]
  [ ! -d "$REPO/.github/ISSUE_TEMPLATE" ]
}

@test "fails when the interns dir is missing" {
  run "$SCRIPT" "$BATS_TEST_TMPDIR/nope"
  [ "$status" -ne 0 ]
}
