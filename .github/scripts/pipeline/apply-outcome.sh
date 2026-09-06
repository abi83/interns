#!/usr/bin/env bash
#
# Perform an issue-pipeline phase's label transition deterministically, keyed
# off the outcome marker the agent wrote. The agent decides the outcome and
# records one word; every status:* / size:* move lives here, so the transition
# is reproducible and the agent never touches lifecycle labels.
#
# Marker word (in <marker-file>):
#   refinement:  refined | needs-attention
#   estimation:  estimated | needs-attention
# A missing or unrecognised marker means the agent exited without finishing its
# phase — fail so the caller's failure handler escalates to a human.
#
# Usage: apply-outcome.sh <phase> <marker-file> [<estimate-comment-file>]
#   phase: refinement | estimation
#   <estimate-comment-file> is required for the estimation "estimated" path —
#   the four scores are read from it and rolled into a size.
#   Env: ISSUE, GITHUB_REPOSITORY, GH_TOKEN

set -euo pipefail
here="$(dirname "${BASH_SOURCE[0]}")"

phase="$1"
marker_file="$2"
comment_file="${3:-}"

outcome=""
[[ -f "$marker_file" ]] && outcome="$(tr -d '[:space:]' <"$marker_file")"

edit() {
  gh issue edit "$ISSUE" --repo "$GITHUB_REPOSITORY" "$@"
}

# Pull "<Low|Mid|High>" from the first line that starts with the criterion
# label, e.g. "TOUCH: Mid — one file". Case-insensitive; roll-up-size.sh
# validates the word.
score() {
  grep -im1 "^$1:" "$comment_file" \
    | sed -E 's/^[^:]*:[[:space:]]*([A-Za-z]+).*/\1/'
}

roll_up_size() {
  local blast touch human review
  blast=$(score "BLAST RADIUS")
  touch=$(score "TOUCH")
  human=$(score "HUMAN INVOLVEMENT")
  review=$(score "REVIEW OVERHEAD")
  if [[ -z "$blast" || -z "$touch" || -z "$human" || -z "$review" ]]; then
    echo "apply-outcome.sh: couldn't find all four scores in $comment_file" >&2
    exit 1
  fi
  local size
  size=$("$here/roll-up-size.sh" "$blast" "$touch" "$human" "$review")
  echo "Rolled ($blast, $touch, $human, $review) -> size:$size" >&2
  printf '%s' "$size"
}

case "$phase:$outcome" in
  refinement:refined)
    edit --remove-label status:needs-refinement --add-label status:refined
    ;;
  refinement:needs-attention)
    edit --remove-label status:needs-refinement --add-label status:needs-attention
    ;;
  estimation:estimated)
    if [[ -z "$comment_file" || ! -f "$comment_file" ]]; then
      echo "apply-outcome.sh: estimate comment file '$comment_file' not found" >&2
      exit 1
    fi
    size=$(roll_up_size)
    edit --remove-label status:refined --add-label status:estimated --add-label "size:$size"
    ;;
  estimation:needs-attention)
    edit --remove-label status:refined --add-label status:needs-attention
    ;;
  *)
    echo "apply-outcome.sh: no usable outcome marker for $phase (got '${outcome:-<none>}')" >&2
    exit 1
    ;;
esac

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "outcome=$outcome" >>"$GITHUB_OUTPUT"
fi
