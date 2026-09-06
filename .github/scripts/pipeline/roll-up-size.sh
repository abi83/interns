#!/usr/bin/env bash
#
# Deterministic scores -> SIZE mapping for the estimate job. The estimator
# outputs only the four Low|Mid|High scores; this script rolls them into one
# size so the mapping is reproducible and testable instead of a judgement the
# agent makes and then re-parses from its own prose.
#
# The tuple collapses to a (#High, #Mid) key — order between the four criteria
# doesn't change the size, only how many landed at each level. One explicit
# lookup table covers every reachable key (#High + #Mid <= 4):
#
#   no Highs        -> Low count drives it: all-Low is XS, a couple of Mids S,
#                      mostly-Mid M
#   one High        -> M, unless the rest are Mid-heavy (-> L)
#   two Highs       -> L  (this is the old prose's "multiple Highs")
#   three+ Highs    -> XL (a High on most criteria at once)
#
# Usage: roll-up-size.sh <blast-radius> <touch> <human-involvement> <review-overhead>
#   each argument Low|Mid|High (case-insensitive); prints XS|S|M|L|XL

set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: roll-up-size.sh <blast-radius> <touch> <human-involvement> <review-overhead>" >&2
  exit 2
fi

highs=0 mids=0
for raw in "$@"; do
  case "${raw,,}" in
    low)  ;;
    mid)  mids=$((mids + 1)) ;;
    high) highs=$((highs + 1)) ;;
    *) echo "roll-up-size.sh: not a Low|Mid|High score: '$raw'" >&2; exit 2 ;;
  esac
done

declare -A SIZE=(
  [0,0]=XS [0,1]=S  [0,2]=S  [0,3]=M  [0,4]=M
  [1,0]=M  [1,1]=M  [1,2]=M  [1,3]=L
  [2,0]=L  [2,1]=L  [2,2]=L
  [3,0]=XL [3,1]=XL
  [4,0]=XL
)

echo "${SIZE[$highs,$mids]}"
