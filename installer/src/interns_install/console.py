"""Terminal I/O: status lines, prompts, and dry-run bookkeeping."""

from __future__ import annotations

import getpass
import sys
from dataclasses import dataclass, field


@dataclass
class Console:
    assume_yes: bool = False
    dry_run: bool = False
    planned: list[str] = field(default_factory=list)
    manual: list[str] = field(default_factory=list)

    def say(self, msg: str) -> None:
        print(f"interns-install: {msg}")

    def warn(self, msg: str) -> None:
        print(f"interns-install: WARNING: {msg}", file=sys.stderr)

    def error(self, msg: str) -> None:
        print(f"interns-install: ERROR: {msg}", file=sys.stderr)

    def step(self, msg: str) -> None:
        print(f"\n→ {msg}")

    def mutation(self, msg: str) -> bool:
        """Record an outward change. Returns False when it must be skipped
        (dry run), True when the caller should perform it."""
        if self.dry_run:
            self.planned.append(msg)
            print(f"  [dry-run] would {msg}")
            return False
        self.planned.append(msg)
        print(f"  {msg}")
        return True

    def note_manual(self, msg: str) -> None:
        self.manual.append(msg)

    def confirm(self, question: str, default: bool = False) -> bool:
        if self.assume_yes:
            return True
        suffix = "Y/n" if default else "y/N"
        try:
            answer = input(f"{question} [{suffix}] ").strip().lower()
        except EOFError:
            return default
        if not answer:
            return default
        return answer in ("y", "yes")

    def prompt(self, question: str) -> str:
        return input(f"{question} ").strip()

    def prompt_secret(self, question: str) -> str:
        return getpass.getpass(f"{question} ").strip()

    def summary(self) -> None:
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        if self.planned:
            label = "Would perform:" if self.dry_run else "Done:"
            print(label)
            for item in self.planned:
                print(f"  - {item}")
        else:
            print("Nothing to do.")
        if self.manual:
            print("\nStill manual:")
            for item in self.manual:
                print(f"  - {item}")
