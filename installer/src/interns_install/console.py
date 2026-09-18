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
        # Write+flush explicitly rather than relying on input()'s own prompt
        # handling: piped through `curl | sh`'s reattached /dev/tty stdin,
        # input()'s implicit prompt write doesn't reliably reach the terminal
        # before it blocks for a line, leaving the operator answering a
        # question they can't see (confirmed hands-on).
        print(f"{question} [{suffix}] ", end="", flush=True)
        try:
            answer = input().strip().lower()
        except EOFError:
            return default
        if not answer:
            return default
        return answer in ("y", "yes")

    def prompt(self, question: str) -> str:
        print(f"{question} ", end="", flush=True)
        return input().strip()

    def prompt_secret(self, question: str) -> str:
        return getpass.getpass(f"{question} ").strip()

    def prompt_multiline_secret(self, question: str) -> str:
        """For PEM keys and other multi-line pastes: getpass reads one line
        only, so a pasted key gets truncated and the remaining lines spill
        onto stdin. Stop at the PEM's own END marker rather than requiring
        EOF (Ctrl-D) -- an invisible keystroke operators kept missing,
        leaving the prompt looking hung after a paste (confirmed hands-on)."""
        print(f"{question}")
        print("  (paste the full PEM value; blank to skip)")
        lines: list[str] = []
        while True:
            try:
                line = input()
            except EOFError:
                break
            if not lines and not line.strip():
                return ""
            lines.append(line)
            if line.strip().startswith("-----END"):
                break
        return "\n".join(lines).strip()

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
