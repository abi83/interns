"""Thin wrappers over the operator's authenticated `gh` CLI.

All repo mutation in the installer goes through here, so it runs with the
operator's own credentials — never a token written to disk.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass


class GhError(RuntimeError):
    pass


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
        raise GhError("the `gh` CLI is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise GhError(f"`gh {' '.join(args)}` failed: {detail}") from exc


def ensure_available() -> None:
    if shutil.which("gh") is None:
        raise GhError("the `gh` CLI is not installed or not on PATH")
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


def api_status(path: str) -> tuple[str, object]:
    """GET `path`. Returns ("ok", body), ("missing", None) for a 404 (the
    resource doesn't exist), or ("blocked", None) for any other error --
    typically a 403 from a token that lacks admin access."""
    try:
        return "ok", api(path)
    except GhError as exc:
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


def list_secret_names(repo: str) -> list[str] | None:
    """None means the token cannot read the secret list (scope-blind)."""
    try:
        data = api(f"repos/{repo}/actions/secrets?per_page=100")
    except GhError:
        return None
    return [s["name"] for s in (data or {}).get("secrets", [])]


def list_variable_names(repo: str) -> list[str] | None:
    try:
        data = api(f"repos/{repo}/actions/variables?per_page=100")
    except GhError:
        return None
    return [v["name"] for v in (data or {}).get("variables", [])]


def set_secret(repo: str, name: str, value: str) -> None:
    _run(["secret", "set", name, "--repo", repo, "--body", "-"], input_text=value)


def set_variable(repo: str, name: str, value: str) -> None:
    # `variable set` refuses to overwrite silently on some versions; delete-then-set is idempotent.
    _run(["variable", "delete", name, "--repo", repo], check=False)
    _run(["variable", "set", name, "--repo", repo, "--body", "-"], input_text=value)


def app_public(slug: str) -> dict | None:
    """Public metadata for the App registered under this slug, or None if no
    such App exists. App names are globally unique, so a hit on the default
    name means minting it again would collide — reuse the existing App instead.
    """
    status, body = api_status(f"apps/{slug}")
    return body if status == "ok" and isinstance(body, dict) else None


def convert_manifest(code: str) -> dict:
    """Exchange the one-time manifest code for the App's credentials.

    Unauthenticated on purpose: GitHub scopes the code to the browser session
    that submitted the manifest, and sending an `Authorization` header makes
    this endpoint 404 even when the token's user is that same account.
    """
    req = urllib.request.Request(
        f"https://api.github.com/app-manifest/{code}/conversions",
        method="POST",
        headers={"Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        raise GhError(
            f"manifest conversion failed (HTTP {exc.code}) — the code is single-use "
            "and expires after an hour; re-run to create the App again"
        ) from exc
    except urllib.error.URLError as exc:
        raise GhError(f"manifest conversion request failed: {exc.reason}") from exc
    if not isinstance(data, dict) or "pem" not in data:
        raise GhError("manifest conversion did not return a private key")
    return data


def workflow_exists(repo: str, workflow: str) -> bool:
    try:
        api(f"repos/{repo}/actions/workflows/{workflow}")
        return True
    except GhError:
        return False


def dispatch_workflow(repo: str, workflow: str, ref: str, inputs: dict[str, str]) -> None:
    args = ["workflow", "run", workflow, "--repo", repo, "--ref", ref]
    for key, value in inputs.items():
        args += ["-f", f"{key}={value}"]
    _run(args)


def get_file(repo: str, path: str, ref: str) -> str:
    """Text content of `path` in `repo` at `ref`, via the contents API."""
    data = api(f"repos/{repo}/contents/{path}?ref={ref}")
    if not isinstance(data, dict) or "content" not in data:
        raise GhError(f"could not read {path} from {repo}@{ref}")
    return base64.b64decode(data["content"]).decode()


def branch_head_sha(repo: str, branch: str) -> str:
    data = api(f"repos/{repo}/git/ref/heads/{branch}")
    if not isinstance(data, dict):
        raise GhError(f"could not resolve heads/{branch} on {repo}")
    return data["object"]["sha"]


def create_branch(repo: str, branch: str, sha: str) -> None:
    api(f"repos/{repo}/git/refs", method="POST",
        fields={"ref": f"refs/heads/{branch}", "sha": sha})


def put_file(repo: str, path: str, content: str, message: str, branch: str) -> None:
    api(f"repos/{repo}/contents/{path}", method="PUT", fields={
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    })


def create_pr(repo: str, head: str, base: str, title: str, body: str) -> str:
    """Open a PR and return its URL."""
    proc = _run(["pr", "create", "--repo", repo, "--head", head, "--base", base,
                 "--title", title, "--body", body])
    return proc.stdout.strip()
