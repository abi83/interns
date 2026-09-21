"""Shared glue for pipeline entrypoints: env access, int args, step outputs."""

import os


class MissingEnvError(SystemExit):
    """Exits the entrypoint with a clear message when a required env var is unset."""


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingEnvError(f"{name} unset")
    return value


def optional_int(value: str) -> int | None:
    return int(value) if value else None


def write_output(key: str, value: str | bool) -> None:
    """Appends `key=value` to $GITHUB_OUTPUT; bools become `true`/`false`."""
    text = str(value).lower() if isinstance(value, bool) else value
    with open(require_env("GITHUB_OUTPUT"), "a") as f:
        f.write(f"{key}={text}\n")
