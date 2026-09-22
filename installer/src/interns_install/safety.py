"""Branch-protection and Pages safety checks.

Runs locally with the operator's admin-scoped `gh` session -- branch
protection and Pages both need admin access, which `GITHUB_TOKEN` never has.

Split with `pipeline/src/pipeline/safety_checks.py`: that module covers
GITHUB_TOKEN-readable state (secret/variable presence); this one covers
admin-only state.
"""

from __future__ import annotations

from collections.abc import Callable

from interns import gh
from interns.steps.append_metrics import BRANCH as METRICS_BRANCH
from interns.steps.append_metrics import FILE as METRICS_FILE

from . import gh_admin
from .console import Console

DEFAULT_BOT_LOGINS = ["github-actions[bot]", "claude[bot]"]

# Require a PR + 1 approval, no force pushes or deletions, no push restrictions.
BASELINE_PROTECTION = {
    "required_status_checks": None,
    "enforce_admins": False,
    "required_pull_request_reviews": {"required_approving_review_count": 1},
    "restrictions": None,
    "allow_force_pushes": False,
    "allow_deletions": False,
}

# pipeline.append_metrics pushes straight to this branch, not via PR -- only
# guard against deletion.
METRICS_PROTECTION = {
    "required_status_checks": None,
    "enforce_admins": False,
    "required_pull_request_reviews": None,
    "restrictions": None,
    "allow_force_pushes": True,
    "allow_deletions": False,
}


class SafetyCheckError(RuntimeError):
    pass


def _protection_violation(body: dict, bot_logins: list[str]) -> str | None:
    """None if `body` (a branch-protection API response) satisfies the
    pipeline's requirement, else a description of what's wrong."""
    if body.get("required_pull_request_reviews") is None:
        return "does not require a pull request review"
    restrictions = body.get("restrictions") or {}
    granted = (
        [u.get("login") for u in restrictions.get("users") or []]
        + [f"@{t.get('slug')}" for t in restrictions.get("teams") or []]
        + [f"{a.get('slug')}[bot]" for a in restrictions.get("apps") or []]
    )
    blocked = [bot for bot in bot_logins if bot in granted]
    if blocked:
        return f"push allowlist grants {', '.join(blocked)}"
    return None


def _apply_when_missing(con: Console, state: str, *, blocked: str, ok: str,
                        action: str, apply: Callable[[], None], failure: str,
                        created: str) -> None:
    """The shared read -> blocked/ok/missing -> mutate -> wrap-error flow.
    `state` is the already-read state ("blocked" / "ok" / "missing")."""
    if state == "blocked":
        raise SafetyCheckError(blocked)
    if state == "ok":
        con.say(ok)
        return
    if not con.mutation(action):
        return
    try:
        apply()
    except gh.GhError as exc:
        raise SafetyCheckError(f"{failure}: {exc}") from exc
    con.say(created)


def _blocked_message(what: str) -> str:
    return f"can't read {what} -- your `gh` session needs admin access to this repo"


def _apply_branch_protection(con: Console, repo: gh_admin.Repo, branch: str, state: str,
                             protection: dict, *, action: str, failure: str) -> None:
    _apply_when_missing(
        con, state,
        blocked=_blocked_message(f"branch protection for '{branch}'"),
        ok=f"branch protection on '{branch}': ok",
        action=action,
        apply=lambda: gh_admin.set_branch_protection(repo.slug, branch, protection),
        failure=failure,
        created=f"branch protection on '{branch}': created",
    )


def check_branch_protection(con: Console, repo: gh_admin.Repo, default_branch: str,
                             handled_externally: bool = False,
                             bot_logins: list[str] | None = None) -> None:
    bots = bot_logins if bot_logins is not None else DEFAULT_BOT_LOGINS
    con.step(f"Branch protection: {default_branch}")

    state, body = gh_admin.branch_protection_state(repo.slug, default_branch)

    if state == "ok":
        violation = _protection_violation(body or {}, bots)
        if violation:
            raise SafetyCheckError(f"branch '{default_branch}' is protected but {violation}")
    if state == "missing" and handled_externally:
        con.say(f"branch '{default_branch}' is unprotected; "
                "--branch-protection-handled-externally was passed, skipping")
        return

    _apply_branch_protection(
        con, repo, default_branch, state, BASELINE_PROTECTION,
        action=f"apply baseline branch protection to '{default_branch}'",
        failure=f"branch '{default_branch}' is unprotected and the baseline could not be applied",
    )


def _create_metrics_branch(repo: gh_admin.Repo) -> None:
    """A parentless commit adding an empty metrics.jsonl, pushed as the
    `metrics` branch -- built through the Git Data API since `gh` has no
    plumbing for orphan commits."""
    blob_sha = gh_admin.create_blob(repo.slug, "")
    tree_sha = gh_admin.create_tree(repo.slug, [
        {"path": METRICS_FILE, "mode": "100644", "type": "blob", "sha": blob_sha},
    ])
    commit_sha = gh_admin.create_commit(
        repo.slug, "chore(metrics): initialize metrics branch", tree_sha, parents=[])
    gh_admin.create_branch(repo.slug, METRICS_BRANCH, commit_sha)


def check_metrics_branch(con: Console, repo: gh_admin.Repo) -> None:
    con.step(f"Metrics branch: {METRICS_BRANCH}")

    if gh_admin.ref_exists(repo.slug, METRICS_BRANCH):
        con.say(f"branch '{METRICS_BRANCH}': already exists")
    else:
        if not con.mutation(f"create orphan branch '{METRICS_BRANCH}' with empty {METRICS_FILE}"):
            return
        try:
            _create_metrics_branch(repo)
        except gh.GhError as exc:
            raise SafetyCheckError(f"could not create '{METRICS_BRANCH}': {exc}") from exc
        con.say(f"branch '{METRICS_BRANCH}': created")

    state, _ = gh_admin.branch_protection_state(repo.slug, METRICS_BRANCH)
    _apply_branch_protection(
        con, repo, METRICS_BRANCH, state, METRICS_PROTECTION,
        action=f"apply deletion protection to '{METRICS_BRANCH}'",
        failure=f"branch '{METRICS_BRANCH}' is unprotected and could not be protected",
    )


def check_pages(con: Console, repo: gh_admin.Repo) -> None:
    con.step("GitHub Pages")

    state, _ = gh_admin.pages_state(repo.slug)
    _apply_when_missing(
        con, state,
        blocked=_blocked_message("GitHub Pages state"),
        ok="GitHub Pages: enabled",
        action="enable GitHub Pages (GitHub Actions build type)",
        apply=lambda: gh_admin.enable_pages(repo.slug),
        failure="GitHub Pages could not be enabled",
        created="GitHub Pages: enabled",
    )
