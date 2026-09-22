"""Stand-in for `gh` and `git`, installed on $PATH by the harness (as `sh` wrappers
running `fake_cli.py <tool> <args>`).

Records every call to $FAKE_CLI_DIR/calls.jsonl and answers from the canned
rules in $FAKE_CLI_DIR/rules.json. A rule matches when all its `args` tokens
appear in the call's argv in order; the most specific wins, ties go to the newest. Unmatched calls fail loudly,
except the state-changing commands in QUIET, which succeed with no output.
"""

import json
import os
import sys
from pathlib import Path

QUIET = {
    "gh": [["issue", "edit"], ["issue", "comment"], ["pr", "edit"], ["pr", "comment"], ["workflow", "run"]],
    "git": [["fetch"], ["reset"], ["commit"], ["push"], ["checkout"]],
}


def _matches(tokens: list[str], argv: list[str]) -> bool:
    remaining = iter(argv)
    return all(token in remaining for token in tokens)


def main() -> int:
    tool, argv = sys.argv[1], sys.argv[2:]
    state = Path(os.environ["FAKE_CLI_DIR"])
    stdin = sys.stdin.read() if "--input" in argv else ""  # only `gh api --input -` is fed on stdin

    def record(unmatched: bool) -> None:
        with open(state / "calls.jsonl", "a") as f:
            f.write(json.dumps({"tool": tool, "argv": argv, "stdin": stdin, "unmatched": unmatched}) + "\n")

    rules = [r for r in json.loads((state / "rules.json").read_text())
             if r["tool"] == tool and _matches(r["args"], argv)]
    if rules:
        record(unmatched=False)
        rule = max(rules, key=lambda r: len(r["args"]))  # rules are stored newest first
        sys.stdout.write(rule["stdout"])
        sys.stderr.write(rule["stderr"])
        return rule["code"]

    if any(argv[: len(prefix)] == prefix for prefix in QUIET[tool]):
        record(unmatched=False)
        return 0
    record(unmatched=True)
    sys.stderr.write(f"fake {tool}: no canned response for {argv}\n")
    return 99


if __name__ == "__main__":
    sys.exit(main())
