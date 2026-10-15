"""Shared glue for entrypoint commands: env access, parsers, int args, step outputs."""

import argparse
import os
import secrets


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

    The delimiter is random and resampled on collision: a fixed one would truncate
    (or corrupt the rest of $GITHUB_OUTPUT after) a value containing it.

    Exactly one newline precedes the closing delimiter (added only if missing):
    Actions treats it as the block's line separator, so a second would leave an
    extra trailing blank line in the value.
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


def build_parser(command: str) -> argparse.ArgumentParser:
    """The parser for a command registered in `interns.entrypoint`; `prog` is derived from its name."""
    return argparse.ArgumentParser(prog=f"interns.entrypoint {command}")
