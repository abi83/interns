"""Posts the spike advisory on a `type:spike` issue after estimation. The
estimate is the end of a spike's pipeline path -- no coder picks it up -- so
the owner needs that spelled out. The notice comes from the workflow, not
the agent: type:spike is known from the issue's labels before the agent
runs, so there's nothing for the agent to decide.

No-op on any other issue type, or a spike not yet estimated.

spike-advisory.sh is a thin shim over this module.
"""

from __future__ import annotations

import sys

from . import gh, labels

ADVISORY = (
    "This is a spike; no coder picks it up. The estimate above is for your "
    "planning — do the investigation and close the issue when done."
)


def post_advisory(repo: str, issue: int) -> str | None:
    """Posts the advisory and returns it, or None (and posts nothing) when
    the issue isn't an estimated spike."""
    current = set(labels.issue_labels(repo, issue))
    if "type:spike" not in current:
        return None
    if "status:estimated" not in current:
        return None
    gh.issue_comment(repo, issue, ADVISORY)
    return ADVISORY


def _main(argv: list[str]) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(prog="python -m pipeline.spike_advisory")
    parser.add_argument("issue", type=int)
    args = parser.parse_args(argv)

    repo = os.environ["GITHUB_REPOSITORY"]
    if post_advisory(repo, args.issue) is None:
        print(f"Issue #{args.issue} is not an estimated spike — no advisory.")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
