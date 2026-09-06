setup() {
  load helpers
  SCRIPT="$PIPELINE_DIR/roll-up-size.sh"
}

size() { run "$SCRIPT" "$@"; [ "$status" -eq 0 ]; echo "$output"; }

@test "all Low is XS" {
  [ "$(size Low Low Low Low)" = XS ]
}

@test "a Mid or two among Lows is S" {
  [ "$(size Mid Low Low Low)" = S ]
  [ "$(size Low Mid Low Mid)" = S ]
}

@test "mostly-Mid is M" {
  [ "$(size Mid Mid Mid Low)" = M ]
  [ "$(size Mid Mid Mid Mid)" = M ]
}

@test "a single High is M" {
  [ "$(size High Low Low Low)" = M ]
  [ "$(size Low Low High Mid)" = M ]
}

@test "one High plus Mid-heavy rest is L" {
  [ "$(size High Mid Mid Mid)" = L ]
}

@test "two Highs is L regardless of the other two (the old 'multiple Highs')" {
  [ "$(size High High Low Low)" = L ]
  [ "$(size High High Mid Mid)" = L ]
}

@test "three or four Highs is XL (High on most criteria at once)" {
  [ "$(size High High High Low)" = XL ]
  [ "$(size High High High High)" = XL ]
}

@test "order of the four scores doesn't change the size" {
  [ "$(size High Low High Mid)" = "$(size Low Mid High High)" ]
}

@test "scores are case-insensitive" {
  [ "$(size low MID high Low)" = "$(size Low Mid High Low)" ]
}

@test "wrong argument count exits 2" {
  run "$SCRIPT" Low Low Low
  [ "$status" -eq 2 ]
}

@test "an unrecognized score exits 2" {
  run "$SCRIPT" Low Low Low Enormous
  [ "$status" -eq 2 ]
  [[ "$output" == *"not a Low|Mid|High score"* ]]
}
