"""Shared wrapper over the `gh` CLI, used by the pipeline scripts, the
`interns-install` CLI and the gh-issues MCP server."""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from dataclasses import dataclass


class GhError(RuntimeError):
    """Base class for all errors raised by this module."""


class GhNotInstalledError(GhError):
    """The `gh` CLI is not installed or not on PATH."""


class GhCommandError(GhError):
    """A `gh` subprocess exited non-zero."""


def _run(args: list[str], *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
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
        raise GhCommandError(f"`gh {' '.join(args)}` failed: {detail}") from exc


def ensure_available() -> None:
    if shutil.which("gh") is None:
        raise GhNotInstalledError("the `gh` CLI is not installed or not on PATH")
    _run(["auth", "status"])


def _parse_scopes(text: str) -> set[str]:
    for line in text.splitlines():
        marker = "Token scopes:"
        if marker in line:
            raw = line.split(marker, 1)[1]
            return {s.strip().strip("'\"") for s in raw.split(",") if s.strip().strip("'\"")}
    return set()


def auth_scopes() -> set[str]:
    """Classic-token scopes from `gh auth status`. Empty for a fine-grained
    PAT (its permissions are not reported here)."""
    proc = _run(["auth", "status"], check=False)
    return _parse_scopes((proc.stderr or "") + (proc.stdout or ""))


def api(path: str, *, method: str = "GET", fields: dict[str, str] | None = None,
        input_json: str | None = None) -> object:
    args = ["api", "-H", "Accept: application/vnd.github+json", "-X", method, path]
    for key, value in (fields or {}).items():
        args += ["-f", f"{key}={value}"]
    if input_json is not None:
        args += ["--input", "-"]
    proc = _run(args, input_text=input_json)
    out = proc.stdout.strip()
    return json.loads(out) if out else None


def graphql(query: str, **variables: str | int) -> dict:
    """Run a GraphQL query. Variables go as `-F`, so gh types numeric values."""
    args = ["api", "graphql", "-f", f"query={query}"]
    for key, value in variables.items():
        args += ["-F", f"{key}={value}"]
    return json.loads(_run(args).stdout)


def api_all_pages(path: str) -> list:
    """Every item across every page of a paginated array endpoint."""
    proc = _run(["api", "-H", "Accept: application/vnd.github+json", "--paginate", "--slurp", path])
    pages = json.loads(proc.stdout)
    items: list = []
    for page in pages:
        items.extend(page)
    return items


def api_status(path: str) -> tuple[str, object]:
    """GET `path`. Returns ("ok", body), ("missing", None) for a 404 (the
    resource doesn't exist), or ("blocked", None) for any other error --
    typically a 403 from a token that lacks admin access."""
    try:
        return "ok", api(path)
    except GhCommandError as exc:
        return ("missing" if "HTTP 404" in str(exc) else "blocked"), None


@dataclass
class Repo:
    owner: str
    name: str
    is_org: bool

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.name}"


def current_repo(explicit: str | None) -> Repo:
    args = ["repo", "view"]
    if explicit:
        args.append(explicit)
    args += ["--json", "name,owner"]
    data = json.loads(_run(args).stdout)
    owner = data["owner"]["login"]
    owner_type = data["owner"].get("type", "")
    return Repo(owner=owner, name=data["name"], is_org=owner_type.lower() == "organization")


def issue_view(repo: str, number: int, fields: list[str]) -> dict:
    """`gh issue view` restricted to `fields`."""
    proc = _run(["issue", "view", str(number), "--repo", repo, "--json", ",".join(fields)])
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
    for label in add_labels or []:
        args += ["--add-label", label]
    for label in remove_labels or []:
        args += ["--remove-label", label]
    return _run(args).stdout


def issue_list(repo: str, *, label: str | None = None, limit: int = 100) -> list[dict]:
    """Open issues (number, title, labels, state), optionally filtered to `label`."""
    args = ["issue", "list", "--repo", repo, "--state", "open",
            "--json", "number,title,labels,state", "--limit", str(limit)]
    if label:
        args += ["--label", label]
    return json.loads(_run(args).stdout)


def pr_view(repo: str, number: int, fields: list[str]) -> dict:
    """`gh pr view` restricted to `fields`."""
    proc = _run(["pr", "view", str(number), "--repo", repo, "--json", ",".join(fields)])
    return json.loads(proc.stdout)


def pr_edit(repo: str, number: int, *, add_labels: list[str] | None = None,
            remove_labels: list[str] | None = None) -> None:
    """`gh pr edit`. A no-op when there's nothing to add or remove."""
    if not add_labels and not remove_labels:
        return
    args = ["pr", "edit", str(number), "--repo", repo]
    for label in add_labels or []:
        args += ["--add-label", label]
    for label in remove_labels or []:
        args += ["--remove-label", label]
    _run(args)


def issue_comment(repo: str, number: int, body: str) -> str:
    """Post a comment; returns gh's output (the comment URL)."""
    return _run(["issue", "comment", str(number), "--repo", repo, "--body", body]).stdout


def pr_comment(repo: str, number: int, body: str) -> str:
    """Post a comment; returns gh's output (the comment URL)."""
    return _run(["pr", "comment", str(number), "--repo", repo, "--body", body]).stdout


def pr_diff_names(repo: str, pr: int) -> list[str]:
    """Names of the files changed by `pr`."""
    proc = _run(["pr", "diff", str(pr), "--repo", repo, "--name-only"])
    return [name for name in proc.stdout.splitlines() if name]


def run_url(repo: str) -> str:
    """Link to the current workflow run, for "see the run" lines in
    comments. Reads the Actions env the workflow already exports."""
    server = os.environ["GITHUB_SERVER_URL"]
    run_id = os.environ["GITHUB_RUN_ID"]
    return f"{server}/{repo}/actions/runs/{run_id}"


def pr_url(repo: str, number: int, *, server_url: str | None = None) -> str:
    """Link to PR `number`. Reads GITHUB_SERVER_URL from the Actions env by
    default; pass `server_url` explicitly for a caller (pipeline.run_summary)
    that already threads it as a parameter rather than reading os.environ
    itself, so it stays independently testable."""
    return f"{server_url or os.environ['GITHUB_SERVER_URL']}/{repo}/pull/{number}"


def pr_checks(repo: str, pr: int) -> list[dict]:
    """Checks on `pr`. Empty list when there's nothing usable yet -- no
    checks reported, or a transient `gh` failure the polling loop should
    just retry past."""
    proc = _run(["pr", "checks", str(pr), "--repo", repo, "--json", "name,bucket,link"], check=False)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def pr_create(repo: str, head: str, base: str, title: str, body: str) -> str:
    """Open a PR and return its URL."""
    proc = _run(["pr", "create", "--repo", repo, "--head", head, "--base", base,
                 "--title", title, "--body", body])
    return proc.stdout.strip()


def _paginated_names(path: str, key: str) -> list[str] | None:
    """Names from every page of a `{key: [...]}` collection endpoint, via
    `gh api --paginate`. None means the token cannot read it (scope-blind)."""
    try:
        proc = _run(["api", "-H", "Accept: application/vnd.github+json",
                     "--paginate", "--jq", f".{key}[].name", path])
    except GhCommandError:
        return None
    return [line for line in proc.stdout.splitlines() if line]


def list_secret_names(repo: str) -> list[str] | None:
    """None means the token cannot read the secret list (scope-blind)."""
    return _paginated_names(f"repos/{repo}/actions/secrets", "secrets")


def list_variable_names(repo: str) -> list[str] | None:
    """None means the token cannot read the variable list (scope-blind)."""
    return _paginated_names(f"repos/{repo}/actions/variables", "variables")


def secret_verb(name: str, existing: list[str] | None) -> str:
    """What a `set_secret(name, ...)` call would do, for status messages --
    "set" when we can't tell (scope-blind), else "add" or "overwrite"."""
    if existing is None:
        return "set"
    return "overwrite" if name in existing else "add"


def default_branch(repo: str) -> str:
    data = api(f"repos/{repo}")
    return data.get("default_branch", "main") if isinstance(data, dict) else "main"


def set_secret(repo: str, name: str, value: str) -> None:
    # `--body -` is a literal value to gh, not a stdin sentinel -- omit it
    # entirely so gh falls back to reading stdin, i.e. `input_text` (interns#94).
    _run(["secret", "set", name, "--repo", repo], input_text=value)


def set_variable(repo: str, name: str, value: str) -> None:
    # `variable set` refuses to overwrite silently on some versions; delete-then-set is idempotent.
    _run(["variable", "delete", name, "--repo", repo], check=False)
    _run(["variable", "set", name, "--repo", repo], input_text=value)


def dispatch_workflow(repo: str, workflow: str, ref: str | None, inputs: dict[str, str]) -> None:
    args = ["workflow", "run", workflow, "--repo", repo]
    if ref:
        args += ["--ref", ref]
    for key, value in inputs.items():
        args += ["-f", f"{key}={value}"]
    _run(args)


def get_file(repo: str, path: str, ref: str) -> str:
    """Text content of `path` in `repo` at `ref`, via the contents API."""
    data = api(f"repos/{repo}/contents/{path}?ref={ref}")
    if not isinstance(data, dict) or "content" not in data:
        raise GhCommandError(f"could not read {path} from {repo}@{ref}")
    return base64.b64decode(data["content"]).decode()


def path_exists(repo: str, path: str, ref: str) -> bool:
    """True when `path` (a file or directory) is present in `repo` at `ref`."""
    status, _ = api_status(f"repos/{repo}/contents/{path}?ref={ref}")
    if status == "blocked":
        raise GhCommandError(f"could not check {path} in {repo}@{ref}")
    return status == "ok"


def list_dir(repo: str, path: str, ref: str) -> list[str]:
    """Names of the entries directly under `path` in `repo` at `ref`."""
    data = api(f"repos/{repo}/contents/{path}?ref={ref}")
    if not isinstance(data, list):
        raise GhCommandError(f"{path} in {repo}@{ref} is not a directory")
    return [entry["name"] for entry in data]


def branch_head_sha(repo: str, branch: str) -> str:
    data = api(f"repos/{repo}/git/ref/heads/{branch}")
    if not isinstance(data, dict):
        raise GhCommandError(f"could not resolve heads/{branch} on {repo}")
    return data["object"]["sha"]


def ref_exists(repo: str, branch: str) -> bool:
    status, _ = api_status(f"repos/{repo}/git/ref/heads/{branch}")
    if status == "blocked":
        raise GhCommandError(f"could not check heads/{branch} on {repo}")
    return status == "ok"


def create_branch(repo: str, branch: str, sha: str) -> None:
    api(f"repos/{repo}/git/refs", method="POST",
        fields={"ref": f"refs/heads/{branch}", "sha": sha})


def create_blob(repo: str, content: str) -> str:
    data = api(f"repos/{repo}/git/blobs", method="POST",
               fields={"content": content, "encoding": "utf-8"})
    if not isinstance(data, dict):
        raise GhCommandError(f"could not create blob in {repo}")
    return data["sha"]


def create_tree(repo: str, entries: list[dict]) -> str:
    data = api(f"repos/{repo}/git/trees", method="POST",
               input_json=json.dumps({"tree": entries}))
    if not isinstance(data, dict):
        raise GhCommandError(f"could not create tree in {repo}")
    return data["sha"]


def create_commit(repo: str, message: str, tree: str, parents: list[str]) -> str:
    data = api(f"repos/{repo}/git/commits", method="POST",
               input_json=json.dumps({"message": message, "tree": tree, "parents": parents}))
    if not isinstance(data, dict):
        raise GhCommandError(f"could not create commit in {repo}")
    return data["sha"]


def get_existing_file(repo: str, path: str, ref: str) -> tuple[str, str] | None:
    """(content, sha) for `path` in `repo` at `ref`, or None if absent."""
    status, data = api_status(f"repos/{repo}/contents/{path}?ref={ref}")
    if status == "missing":
        return None
    if status == "blocked" or not isinstance(data, dict) or "content" not in data:
        raise GhCommandError(f"could not read {path} from {repo}@{ref}")
    return base64.b64decode(data["content"]).decode(), data["sha"]


def put_file(repo: str, path: str, content: str, message: str, branch: str,
             sha: str | None = None) -> None:
    """Create `path` on `branch`, or update it when `sha` is given."""
    fields = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if sha is not None:
        fields["sha"] = sha
    api(f"repos/{repo}/contents/{path}", method="PUT", fields=fields)


def label_list(repo: str) -> list[dict]:
    proc = _run(["label", "list", "--repo", repo, "--limit", "500",
                 "--json", "name,color,description"])
    return json.loads(proc.stdout)


def label_names(repo: str) -> list[str]:
    return [entry["name"] for entry in label_list(repo)]


def label_create(repo: str, name: str, color: str, description: str) -> None:
    _run(["label", "create", name, "--repo", repo, "--color", color, "--description", description])


def label_edit(repo: str, name: str, color: str, description: str) -> None:
    _run(["label", "edit", name, "--repo", repo, "--color", color, "--description", description])
