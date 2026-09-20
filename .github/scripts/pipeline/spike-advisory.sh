#!/usr/bin/env bash
#
# Post the spike advisory on a `type:spike` issue after estimation. The estimate
# is the end of a spike's pipeline path — no coder picks it up — so the owner
# needs that spelled out. The notice comes from the workflow, not the agent:
# type:spike is known from the issue's labels before the agent runs, so there's
# nothing for the agent to decide.
#
# No-op on any other issue type.
#
# Usage: spike-advisory.sh
#   Env: ISSUE, GITHUB_REPOSITORY, GH_TOKEN

set -euo pipefail
# shellcheck source=.github/scripts/pipeline/lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

labels=$(issue_labels_csv "$ISSUE")

if [[ ",$labels," != *",type:spike,"* ]]; then
  echo "Issue #$ISSUE is not a spike — no advisory."
  exit 0
fi

if [[ ",$labels," != *",status:estimated,"* ]]; then
  echo "Issue #$ISSUE is a spike but not yet estimated — no advisory."
  exit 0
fi

gh issue comment "$ISSUE" --repo "$GITHUB_REPOSITORY" --body \
  "This is a spike; no coder picks it up. The estimate above is for your planning — do the investigation and close the issue when done."
