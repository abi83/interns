"""Collect secrets from the terminal without routing them through Console."""

from __future__ import annotations

import getpass


def prompt_secret(question: str) -> str:
    return getpass.getpass(f"{question} ").strip()


def prompt_multiline_secret(question: str) -> str:
    """For PEM keys and other multi-line pastes: getpass reads one line
    only, so a pasted key gets truncated and the remaining lines spill
    onto stdin. Stop at the PEM's own END marker rather than requiring
    EOF (Ctrl-D) — an invisible keystroke operators kept missing,
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
