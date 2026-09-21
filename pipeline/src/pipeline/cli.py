"""Shared glue for pipeline entrypoints: env access, int args, step outputs."""

import os
import secrets
import sys
from typing import Callable


class MissingEnvError(RuntimeError):
    """A required env var is unset or empty."""


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingEnvError(f"{name} unset")
    return value


def optional_int(value: str) -> int | None:
    return int(value) if value else None


def github_output_block(name: str, content: bytes) -> bytes:
    """A `$GITHUB_OUTPUT`-formatted `name<<DELIM` block holding `content`.

    The delimiter is randomized and resampled until it doesn't collide with
    the content -- a fixed delimiter would silently truncate (or misparse
    the rest of $GITHUB_OUTPUT after) a value that happens to contain it.

    Exactly one newline separates the content from the closing delimiter
    line (added only if the content doesn't already end in one) -- GitHub
    Actions' multiline-output parsing treats that newline as the block's own
    line separator, not part of the value, so adding a second one would
    leave the parsed value with an extra trailing blank line.
    """
    delim = f"ghadelim_{secrets.token_hex(16)}".encode()
    while delim in content:
        delim = f"ghadelim_{secrets.token_hex(16)}".encode()
    if not content.endswith(b"\n"):
        content += b"\n"
    return f"{name}<<".encode() + delim + b"\n" + content + delim + b"\n"


def append_output(entry: bytes) -> None:
    with open(require_env("GITHUB_OUTPUT"), "ab") as f:
        f.write(entry)


def write_output(key: str, value: str | bool | bytes) -> None:
    """Appends an output to $GITHUB_OUTPUT: bools become `true`/`false`, and
    any value containing a newline uses the delimiter form so it can't inject
    further outputs."""
    if isinstance(value, bool):
        value = str(value).lower()
    raw = value if isinstance(value, bytes) else value.encode()
    append_output(github_output_block(key, raw) if b"\n" in raw else f"{key}=".encode() + raw + b"\n")


def run(main: Callable[[list[str]], int]) -> int:
    """Runs an entrypoint's `_main` on sys.argv, turning a missing env var into a clean exit."""
    try:
        return main(sys.argv[1:])
    except MissingEnvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
