"""Stand-in for `gh` and `git`, installed on $PATH by the harness.

Records every call to $FAKE_CLI_DIR/calls.jsonl and answers from the canned
rules in $FAKE_CLI_DIR/rules.json. A rule matches when all its `args` tokens
appear in the call's argv; the most specific wins, ties go to the newest. Unmatched calls fail loudly,
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
    return all(token in argv for token in tokens)


def main() -> int:
    tool = Path(sys.argv[0]).name
    argv = sys.argv[1:]
    state = Path(os.environ["FAKE_CLI_DIR"])
    stdin = "" if sys.stdin.isatty() else sys.stdin.read()

    with open(state / "calls.jsonl", "a") as f:
        f.write(json.dumps({"tool": tool, "argv": argv, "stdin": stdin}) + "\n")

    rules = [r for r in json.loads((state / "rules.json").read_text())
             if r["tool"] == tool and _matches(r["args"], argv)]
    if rules:
        rule = max(rules, key=lambda r: len(r["args"]))  # rules are stored newest first
        sys.stdout.write(rule["stdout"])
        sys.stderr.write(rule["stderr"])
        return rule["code"]

    if any(argv[: len(prefix)] == prefix for prefix in QUIET[tool]):
        return 0
    sys.stderr.write(f"fake {tool}: no canned response for {argv}\n")
    return 99


if __name__ == "__main__":
    sys.exit(main())
