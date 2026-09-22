"""Raw `gh` CLI transport: subprocess execution, error types, and the REST
and GraphQL primitives. No domain knowledge lives here — only the mechanics
of speaking to the `gh` CLI and surfacing failures as typed exceptions.

Higher-level issue/PR/label operations live in `pipeline.gh`. Admin-scoped
installer operations live in `interns_install.gh_admin`."""

from __future__ import annotations

import json
import subprocess


class GhError(RuntimeError):
    """Base class for all errors raised by this module."""


class GhNotInstalledError(GhError):
    """The `gh` CLI is not installed or not on PATH."""


class GhCommandError(GhError):
    """A `gh` subprocess exited non-zero."""


def _subcommand(args: list[str]) -> str:
    """Leading non-flag tokens of `args`, so error messages name the command
    without echoing bodies or query payloads."""
    tokens = []
    for arg in args:
        if arg.startswith("-"):
            break
        tokens.append(arg)
    return " ".join(tokens[:3])


def run(args: list[str], *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["gh", *args],
            input=input_text,
            capture_output=True,
            text=True,
            check=check,
        )
    except FileNotFoundError as exc:
        raise GhNotInstalledError("the `gh` CLI is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise GhCommandError(f"`gh {_subcommand(args)}` failed: {detail}") from exc


def api(path: str, *, method: str = "GET", fields: dict[str, str] | None = None,
        input_json: str | None = None) -> object:
    args = ["api", "-H", "Accept: application/vnd.github+json", "-X", method, path]
    for key, value in (fields or {}).items():
        args += ["-f", f"{key}={value}"]
    if input_json is not None:
        args += ["--input", "-"]
    proc = run(args, input_text=input_json)
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def graphql(query: str, **variables: str | int) -> dict:
    """Run a GraphQL query. Variables go as `-F`, so gh types numeric values."""
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        args += ["-F", f"{key}={value}"]
    return json.loads(run(args).stdout)


def api_all_pages(path: str) -> list:
    """Every item across every page of a paginated array endpoint."""
    proc = run(["api", "-H", "Accept: application/vnd.github+json", "--paginate", "--slurp", path])
    pages = json.loads(proc.stdout)
    items: list = []
    for page in pages:
        items.extend(page)
    return items


def api_status(path: str) -> tuple[str, object]:
    """GET `path`. Returns ("ok", body), ("missing", None) for a 404, or
    ("blocked", None) for a 403. Any other failure raises."""
    try:
        return "ok", api(path)
    except GhCommandError as exc:
        if "HTTP 404" in str(exc):
            return "missing", None
        if "HTTP 403" in str(exc):
            return "blocked", None
        raise
