"""Issue/PR/label/review/check operations over the `gh` CLI, shared by the pipeline
steps and the gh-issues MCP server. The raw transport lives in `interns.gh.transport`.

Transport primitives are re-imported here for this module's own use; patch them at
`interns.gh.transport.*`, not `interns.gh.ops.*`."""

from __future__ import annotations

import json
from urllib.parse import quote

from .transport import (
    GhCommandError,
    GhError,
    GhNotInstalledError,
    api,
    api_all_pages,
    graphql,
    run,
)

__all__ = [
    "GhCommandError", "GhError", "GhNotInstalledError",
    "InvalidInputError", "PushRefusedError",
    "issue_view", "issue_edit", "issue_edit_validated", "issue_list", "issue_comment",
    "pr_view", "pr_rest", "pr_list", "pr_edit", "pr_comment", "pr_diff", "pr_diff_names", "pr_checks", "job_log", "pr_create",
    "pr_submit_review", "pr_for_head", "pr_ready", "pr_update",
    "issue_with_relations", "pr_reviews", "pr_review_comments", "issue_comments_all",
    "default_branch", "dispatch_workflow", "collaborator_permission",
    "label_list", "label_create", "label_edit",
    "list_secret_names", "list_variable_names",
]


class InvalidInputError(ValueError):
    """Caller-supplied arguments are malformed or fail validation."""


class PushRefusedError(RuntimeError):
    """push_branch refused: protected branch, nothing to push, or a protected path."""


_ISSUE_WITH_RELATIONS_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      number
      title
      body
      state
      labels(first: 20) { nodes { name } }
      comments(first: 50) {
        nodes { author { login } createdAt body }
      }
      parent          { number title state }
      subIssues(first: 20) { nodes { number title state } }
      blockedBy(first: 20) { nodes { number title state } }
      blocking(first: 20)  { nodes { number title state } }
    }
  }
}
"""


def _label_flags(add_labels: list[str] | None, remove_labels: list[str] | None) -> list[str]:
    return [
        *(arg for label in add_labels or [] for arg in ("--add-label", label)),
        *(arg for label in remove_labels or [] for arg in ("--remove-label", label)),
    ]


def issue_view(repo: str, number: int, fields: list[str]) -> dict:
    """`gh issue view` restricted to `fields`."""
    proc = run(["issue", "view", str(number), "--repo", repo, "--json", ",".join(fields)])
    return json.loads(proc.stdout)


def issue_with_relations(repo: str, number: int) -> dict:
    """The raw GraphQL issue node: labels, comments and parent/sub-issue/blocking
    relationships. Raises InvalidInputError when `number` is not an issue."""
    owner, name = repo.split("/", 1)
    data = graphql(_ISSUE_WITH_RELATIONS_QUERY, owner=owner, repo=name, number=number)
    issue = data["data"]["repository"]["issue"]
    if issue is None:
        raise InvalidInputError(f"#{number} is not an issue (it is a pull request or does not exist)")
    return issue


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


def issue_edit_validated(repo: str, number: int, *, body: str, title: str | None = None) -> str:
    """Edit an issue body (and optionally title), with title validation.

    Raises InvalidInputError if title contains newlines.
    Returns a human-readable success string.
    """
    if title is not None and "\n" in title:
        raise InvalidInputError("Title must be a single line")
    output = issue_edit(repo, number, body=body, title=title)
    updated = ["body"] + (["title"] if title is not None else [])
    return output or f"Updated {' and '.join(updated)} on issue #{number}"


def issue_list(repo: str, *, label: str | None = None) -> list[dict]:
    """Every open issue (number, title, labels, state), optionally filtered to
    `label`. Pull requests are excluded."""
    path = f"repos/{repo}/issues?state=open&per_page=100"
    if label:
        path += f"&labels={quote(label, safe='')}"
    return [
        {"number": i["number"], "title": i["title"], "labels": [label["name"] for label in i["labels"]], "state": i["state"].upper()}
        for i in api_all_pages(path)
        if "pull_request" not in i
    ]


def pr_view(repo: str, number: int, fields: list[str]) -> dict:
    """`gh pr view` restricted to `fields`."""
    proc = run(["pr", "view", str(number), "--repo", repo, "--json", ",".join(fields)])
    return json.loads(proc.stdout)


def pr_rest(repo: str, number: int) -> dict:
    """The pull request as the REST API returns it: state, draft flag, head and author (login and type)."""
    result = api(f"repos/{repo}/pulls/{number}")
    if not isinstance(result, dict):
        raise GhCommandError(f"unexpected response from pulls endpoint: {result!r}")
    return result


def collaborator_permission(repo: str, login: str) -> str:
    """The user's permission on `repo`: admin, write, read or none. Raises when it cannot be resolved."""
    try:
        result = api(f"repos/{repo}/collaborators/{quote(login, safe='')}/permission")
    except GhCommandError as exc:
        raise GhError(f"cannot resolve {login}'s permission on {repo}: {exc}") from exc
    if not isinstance(result, dict) or not isinstance(result.get("permission"), str):
        raise GhError(f"cannot resolve {login}'s permission on {repo}: unexpected response {result!r}")
    return result["permission"]


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


def pr_diff(repo: str, pr: int) -> str:
    """The unified diff as the API returns it, covering every changed path."""
    return run(["pr", "diff", str(pr), "--repo", repo]).stdout


def pr_diff_names(repo: str, pr: int) -> list[str]:
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


def job_log(repo: str, job_id: int) -> str:
    return run(["run", "view", "--repo", repo, f"--job={job_id}", "--log"]).stdout


def pr_create(repo: str, head: str, base: str, title: str, body: str, *, draft: bool = False) -> str:
    """Open a PR and return its URL."""
    args = ["pr", "create", "--repo", repo, "--head", head, "--base", base,
            "--title", title, "--body", body]
    if draft:
        args.append("--draft")
    return run(args).stdout.strip()


def pr_for_head(repo: str, head: str) -> dict | None:
    """The open PR whose head branch is `head` (`number`, `url`, `isDraft`), or None."""
    proc = run(["pr", "list", "--repo", repo, "--head", head, "--state", "open",
                "--json", "number,url,isDraft"])
    prs = json.loads(proc.stdout)
    return prs[0] if prs else None


def pr_update(repo: str, number: int, *, title: str, body: str) -> None:
    run(["pr", "edit", str(number), "--repo", repo, "--title", title, "--body", body])


def pr_ready(repo: str, number: int) -> None:
    run(["pr", "ready", str(number), "--repo", repo])


def pr_reviews(repo: str, pr: int) -> list:
    """Every review on `pr`, across every page, oldest first."""
    return api_all_pages(f"repos/{repo}/pulls/{pr}/reviews")


def pr_review_comments(repo: str, pr: int) -> list:
    """Every line-anchored review comment on `pr`, across every page."""
    return api_all_pages(f"repos/{repo}/pulls/{pr}/comments")


def issue_comments_all(repo: str, number: int) -> list:
    """Every conversation comment on an issue or PR, across every page."""
    return api_all_pages(f"repos/{repo}/issues/{number}/comments")


def pr_submit_review(repo: str, pr: int, event: str, body: str,
                     comments: list[dict] | None = None) -> dict:
    """Submit a formal PR review atomically. Raises InvalidInputError for unrecognised events."""
    if event not in ("APPROVE", "REQUEST_CHANGES"):
        raise InvalidInputError("event must be APPROVE or REQUEST_CHANGES")
    payload = json.dumps({"event": event, "body": body, "comments": comments or []})
    result = api(f"repos/{repo}/pulls/{pr}/reviews", method="POST", input_json=payload)
    if not isinstance(result, dict):
        raise GhCommandError(f"unexpected response from reviews endpoint: {result!r}")
    return result


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
        {"name": lbl["name"], "color": lbl["color"], "description": lbl["description"]}
        for lbl in api_all_pages(f"repos/{repo}/labels?per_page=100")
    ]


def label_create(repo: str, name: str, color: str, description: str) -> None:
    run(["label", "create", name, "--repo", repo, "--color", color, "--description", description])


def label_edit(repo: str, name: str, color: str, description: str) -> None:
    run(["label", "edit", name, "--repo", repo, "--color", color, "--description", description])
