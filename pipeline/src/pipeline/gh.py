"""Wrapper over the `gh` CLI shared by the pipeline scripts, the gh-issues
MCP server and the `interns-install` CLI. Installer-only admin calls live in
`interns_install.gh_admin`."""

from __future__ import annotations

import json
import subprocess
from urllib.parse import quote


class GhError(RuntimeError):
    """Base class for all errors raised by this module."""


class GhNotInstalledError(GhError):
    """The `gh` CLI is not installed or not on PATH."""


class GhCommandError(GhError):
    """A `gh` subprocess exited non-zero."""


def _subcommand(args: list[str]) -> str:
    """Leading non-flag tokens of `args` (e.g. `issue edit 5`), so error
    messages name the command without echoing bodies or query payloads."""
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
    """GET `path`. Returns ("ok", body), ("missing", None) for a 404 (the
    resource doesn't exist), or ("blocked", None) for a 403 (a token that
    lacks admin access). Any other failure -- network, auth, 5xx -- raises."""
    try:
        return "ok", api(path)
    except GhCommandError as exc:
        if "HTTP 404" in str(exc):
            return "missing", None
        if "HTTP 403" in str(exc):
            return "blocked", None
        raise


def _label_flags(add_labels: list[str] | None, remove_labels: list[str] | None) -> list[str]:
    return [
        *(arg for label in add_labels or [] for arg in ("--add-label", label)),
        *(arg for label in remove_labels or [] for arg in ("--remove-label", label)),
    ]


def issue_view(repo: str, number: int, fields: list[str]) -> dict:
    """`gh issue view` restricted to `fields`."""
    proc = run(["issue", "view", str(number), "--repo", repo, "--json", ",".join(fields)])
    return json.loads(proc.stdout)


def issue_edit(repo: str, number: int, *, body: str | None = None, title: str | None = None,
               add_labels: list[str] | None = None, remove_labels: list[str] | None = None) -> str:
    """`gh issue edit`. A no-op (empty output) when there's nothing to change."""
    if body is None and title is None and not add_labels and not remove_labels:
        return ""
    args = ["issue", "edit", str(number), "--repo", repo]
    if body is not None:
        args += ["--body", body]
    if title is not None:
        args += ["--title", title]
    args += _label_flags(add_labels, remove_labels)
    return run(args).stdout


def issue_list(repo: str, *, label: str | None = None) -> list[dict]:
    """Every open issue (number, title, labels, state), optionally filtered to
    `label`. Pull requests are excluded."""
    path = f"repos/{repo}/issues?state=open&per_page=100"
    if label:
        path += f"&labels={quote(label, safe='')}"
    return [
        {"number": i["number"], "title": i["title"], "labels": i["labels"], "state": i["state"].upper()}
        for i in api_all_pages(path)
        if "pull_request" not in i
    ]


def pr_view(repo: str, number: int, fields: list[str]) -> dict:
    """`gh pr view` restricted to `fields`."""
    proc = run(["pr", "view", str(number), "--repo", repo, "--json", ",".join(fields)])
    return json.loads(proc.stdout)


_PR_LIST_LIMIT = 1000


def pr_list(repo: str, fields: list[str], *, state: str = "open") -> list[dict]:
    """`gh pr list` restricted to `fields`. Raises rather than silently
    dropping PRs when the repo has more than the limit `gh` can return."""
    proc = run(["pr", "list", "--repo", repo, "--state", state, "--limit", str(_PR_LIST_LIMIT),
                 "--json", ",".join(fields)])
    prs = json.loads(proc.stdout)
    if len(prs) >= _PR_LIST_LIMIT:
        raise GhError(f"{repo} has at least {_PR_LIST_LIMIT} {state} PRs; the list would be truncated")
    return prs


def pr_edit(repo: str, number: int, *, add_labels: list[str] | None = None,
            remove_labels: list[str] | None = None) -> None:
    """`gh pr edit`. A no-op when there's nothing to add or remove."""
    if not add_labels and not remove_labels:
        return
    args = ["pr", "edit", str(number), "--repo", repo]
    args += _label_flags(add_labels, remove_labels)
    run(args)


def issue_comment(repo: str, number: int, body: str) -> str:
    """Post a comment; returns gh's output (the comment URL)."""
    return run(["issue", "comment", str(number), "--repo", repo, "--body", body]).stdout


def pr_comment(repo: str, number: int, body: str) -> str:
    """Post a comment; returns gh's output (the comment URL)."""
    return run(["pr", "comment", str(number), "--repo", repo, "--body", body]).stdout


def pr_diff_names(repo: str, pr: int) -> list[str]:
    """Names of the files changed by `pr`."""
    proc = run(["pr", "diff", str(pr), "--repo", repo, "--name-only"])
    return [name for name in proc.stdout.splitlines() if name]


def pr_checks(repo: str, pr: int) -> list[dict]:
    """Checks on `pr`. Empty when none are reported yet; any other failure
    or malformed output raises. `gh pr checks` exits non-zero for failing or
    pending checks but still prints the JSON, so the exit code is ignored."""
    proc = run(["pr", "checks", str(pr), "--repo", repo, "--json", "name,bucket,link"], check=False)
    if not proc.stdout.strip():
        if "no checks reported" in proc.stderr:
            return []
        raise GhCommandError(f"`gh pr checks` failed: {proc.stderr.strip()}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise GhCommandError(f"`gh pr checks` returned invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise GhCommandError("`gh pr checks` returned a non-list body")
    return data


def pr_create(repo: str, head: str, base: str, title: str, body: str) -> str:
    """Open a PR and return its URL."""
    proc = run(["pr", "create", "--repo", repo, "--head", head, "--base", base,
                 "--title", title, "--body", body])
    return proc.stdout.strip()


def _paginated_names(path: str, key: str) -> list[str]:
    """Names from every page of a `{key: [...]}` collection endpoint, via
    `gh api --paginate`. Raises GhCommandError when the token lacks scope."""
    proc = run(["api", "-H", "Accept: application/vnd.github+json",
                 "--paginate", "--jq", f".{key}[].name", path])
    return [line for line in proc.stdout.splitlines() if line]


def list_secret_names(repo: str) -> list[str]:
    """Raises GhCommandError when the token cannot read the secret list."""
    return _paginated_names(f"repos/{repo}/actions/secrets", "secrets")


def list_variable_names(repo: str) -> list[str]:
    """Raises GhCommandError when the token cannot read the variable list."""
    return _paginated_names(f"repos/{repo}/actions/variables", "variables")


def default_branch(repo: str) -> str:
    data = api(f"repos/{repo}")
    if not isinstance(data, dict) or "default_branch" not in data:
        raise GhCommandError(f"could not read the default branch of {repo}")
    return data["default_branch"]


def dispatch_workflow(repo: str, workflow: str, ref: str | None, inputs: dict[str, str]) -> None:
    args = ["workflow", "run", workflow, "--repo", repo]
    if ref:
        args += ["--ref", ref]
    for key, value in inputs.items():
        args += ["-f", f"{key}={value}"]
    run(args)


def label_list(repo: str) -> list[dict]:
    return [
        {"name": l["name"], "color": l["color"], "description": l["description"]}
        for l in api_all_pages(f"repos/{repo}/labels?per_page=100")
    ]


def label_names(repo: str) -> list[str]:
    return [entry["name"] for entry in label_list(repo)]


def label_create(repo: str, name: str, color: str, description: str) -> None:
    run(["label", "create", name, "--repo", repo, "--color", color, "--description", description])


def label_edit(repo: str, name: str, color: str, description: str) -> None:
    run(["label", "edit", name, "--repo", repo, "--color", color, "--description", description])
