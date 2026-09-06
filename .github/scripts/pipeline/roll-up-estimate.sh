#!/usr/bin/env bash
#
# Estimate-job glue: read the four scores out of the estimator's comment file,
# roll them into a size with roll-up-size.sh, and apply the labels the agent no
# longer touches — `size:<SIZE>` plus the status:refined -> status:estimated
# swap. Keeping the mapping and the label write here (not in the agent) makes
# the size reproducible from the four scores alone.
#
# Usage: roll-up-estimate.sh <comment-file>
#   Env: ISSUE, GITHUB_REPOSITORY, GH_TOKEN

set -euo pipefail

comment="$1"
here="$(dirname "${BASH_SOURCE[0]}")"

# Pull "<Low|Mid|High>" from the first line that starts with the criterion
# label, e.g. "TOUCH: Mid — one file". Case-insensitive label match; the score
# word itself is handed to roll-up-size.sh, which validates it.
score() {
  grep -im1 "^$1:" "$comment" \
    | sed -E 's/^[^:]*:[[:space:]]*([A-Za-z]+).*/\1/'
}

blast_radius=$(score "BLAST RADIUS")
touch=$(score "TOUCH")
human=$(score "HUMAN INVOLVEMENT")
review=$(score "REVIEW OVERHEAD")

if [[ -z "$blast_radius" || -z "$touch" || -z "$human" || -z "$review" ]]; then
  echo "roll-up-estimate.sh: couldn't find all four scores in $comment" >&2
  exit 1
fi

size=$("$here/roll-up-size.sh" "$blast_radius" "$touch" "$human" "$review")
echo "Rolled ($blast_radius, $touch, $human, $review) -> size:$size"

gh issue edit "$ISSUE" --repo "$GITHUB_REPOSITORY" \
  --remove-label status:refined \
  --add-label status:estimated \
  --add-label "size:$size"
