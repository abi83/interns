"""Admin-scoped `gh` calls used only by the installer: secrets, variables,
the Git Data API, contents writes, branch protection and Pages. Built on the
shared transport in `pipeline.gh_transport`."""

from __future__ import annotations

import base64
import json
import shutil
from dataclasses import dataclass

from pipeline import gh_transport as gh


def ensure_available() -> None:
    if shutil.which("gh") is None:
        raise gh.GhNotInstalledError("the `gh` CLI is not installed or not on PATH")
    gh.run(["auth", "status"])


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
    proc = gh.run(["auth", "status"], check=False)
    return _parse_scopes((proc.stderr or "") + (proc.stdout or ""))


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
    data = json.loads(gh.run(args).stdout)
    owner = data["owner"]["login"]
    name = data["name"]
    # `repo view --json owner` carries only id and login, not the owner type.
    owner_type = gh.api(f"repos/{owner}/{name}")["owner"]["type"]
    return Repo(owner=owner, name=name, is_org=owner_type == "Organization")


def secret_verb(name: str, existing: list[str] | None) -> str:
    """What a `set_secret(name, ...)` call would do, for status messages --
    "set" when we can't tell (scope-blind), else "add" or "overwrite"."""
    if existing is None:
        return "set"
    return "overwrite" if name in existing else "add"


def set_secret(repo: str, name: str, value: str) -> None:
    # `--body -` is a literal value to gh, not a stdin sentinel -- omit it
    # entirely so gh falls back to reading stdin, i.e. `input_text` (interns#94).
    gh.run(["secret", "set", name, "--repo", repo], input_text=value)


def set_variable(repo: str, name: str, value: str) -> None:
    # `variable set` refuses to overwrite silently on some versions; delete-then-set is idempotent.
    try:
        gh.run(["variable", "delete", name, "--repo", repo])
    except gh.GhCommandError as exc:
        if "HTTP 404" not in str(exc):
            raise
    gh.run(["variable", "set", name, "--repo", repo], input_text=value)


def get_file(repo: str, path: str, ref: str) -> str:
    """Text content of `path` in `repo` at `ref`, via the contents API."""
    data = gh.api(f"repos/{repo}/contents/{path}?ref={ref}")
    if not isinstance(data, dict) or "content" not in data:
        raise gh.GhCommandError(f"could not read {path} from {repo}@{ref}")
    return base64.b64decode(data["content"]).decode()


def path_exists(repo: str, path: str, ref: str) -> bool:
    """True when `path` (a file or directory) is present in `repo` at `ref`."""
    status, _ = gh.api_status(f"repos/{repo}/contents/{path}?ref={ref}")
    if status == "blocked":
        raise gh.GhCommandError(f"could not check {path} in {repo}@{ref}")
    return status == "ok"


def list_dir(repo: str, path: str, ref: str) -> list[str]:
    """Names of the entries directly under `path` in `repo` at `ref`."""
    data = gh.api(f"repos/{repo}/contents/{path}?ref={ref}")
    if not isinstance(data, list):
        raise gh.GhCommandError(f"{path} in {repo}@{ref} is not a directory")
    return [entry["name"] for entry in data]


def branch_head_sha(repo: str, branch: str) -> str:
    data = gh.api(f"repos/{repo}/git/ref/heads/{branch}")
    if not isinstance(data, dict):
        raise gh.GhCommandError(f"could not resolve heads/{branch} on {repo}")
    return data["object"]["sha"]


def ref_exists(repo: str, branch: str) -> bool:
    status, _ = gh.api_status(f"repos/{repo}/git/ref/heads/{branch}")
    if status == "blocked":
        raise gh.GhCommandError(f"could not check heads/{branch} on {repo}")
    return status == "ok"


def create_branch(repo: str, branch: str, sha: str) -> None:
    gh.api(f"repos/{repo}/git/refs", method="POST",
        fields={"ref": f"refs/heads/{branch}", "sha": sha})


def create_blob(repo: str, content: str) -> str:
    data = gh.api(f"repos/{repo}/git/blobs", method="POST",
               fields={"content": content, "encoding": "utf-8"})
    if not isinstance(data, dict):
        raise gh.GhCommandError(f"could not create blob in {repo}")
    return data["sha"]


def create_tree(repo: str, entries: list[dict]) -> str:
    data = gh.api(f"repos/{repo}/git/trees", method="POST",
               input_json=json.dumps({"tree": entries}))
    if not isinstance(data, dict):
        raise gh.GhCommandError(f"could not create tree in {repo}")
    return data["sha"]


def create_commit(repo: str, message: str, tree: str, parents: list[str]) -> str:
    data = gh.api(f"repos/{repo}/git/commits", method="POST",
               input_json=json.dumps({"message": message, "tree": tree, "parents": parents}))
    if not isinstance(data, dict):
        raise gh.GhCommandError(f"could not create commit in {repo}")
    return data["sha"]


def get_existing_file(repo: str, path: str, ref: str) -> tuple[str, str] | None:
    """(content, sha) for `path` in `repo` at `ref`, or None if absent."""
    status, data = gh.api_status(f"repos/{repo}/contents/{path}?ref={ref}")
    if status == "missing":
        return None
    if status == "blocked" or not isinstance(data, dict) or "content" not in data:
        raise gh.GhCommandError(f"could not read {path} from {repo}@{ref}")
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
    gh.api(f"repos/{repo}/contents/{path}", method="PUT", fields=fields)


def branch_protection_state(repo: str, branch: str) -> tuple[str, object]:
    """`gh.api_status` of the branch's protection: ("ok", body), ("missing", None)
    or ("blocked", None)."""
    return gh.api_status(f"repos/{repo}/branches/{branch}/protection")


def set_branch_protection(repo: str, branch: str, protection: dict) -> None:
    gh.api(f"repos/{repo}/branches/{branch}/protection",
           method="PUT", input_json=json.dumps(protection))


def pages_state(repo: str) -> tuple[str, object]:
    """`gh.api_status` of the repo's Pages site."""
    return gh.api_status(f"repos/{repo}/pages")


def enable_pages(repo: str) -> None:
    """Enable Pages with the GitHub Actions build type."""
    gh.api(f"repos/{repo}/pages", method="POST", fields={"build_type": "workflow"})
