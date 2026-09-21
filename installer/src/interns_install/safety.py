"""Branch-protection and Pages safety checks.

Runs locally with the operator's admin-scoped `gh` session -- branch
protection and Pages both need admin access, which `GITHUB_TOKEN` never has.

Split with `pipeline/src/pipeline/safety_checks.py`: that module covers
GITHUB_TOKEN-readable state (secret/variable presence); this one covers
admin-only state.
"""

from __future__ import annotations

import json

from . import gh
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

METRICS_BRANCH = "metrics"
METRICS_FILE = "metrics.jsonl"

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


def check_branch_protection(con: Console, repo: gh.Repo, default_branch: str,
                             handled_externally: bool = False,
                             bot_logins: list[str] | None = None) -> None:
    bots = bot_logins if bot_logins is not None else DEFAULT_BOT_LOGINS
    con.step(f"Branch protection: {default_branch}")

    state, body = gh.api_status(f"repos/{repo.slug}/branches/{default_branch}/protection")

    if state == "blocked":
        raise SafetyCheckError(
            f"can't read branch protection for '{default_branch}' -- "
            "your `gh` session needs admin access to this repo"
        )

    if state == "ok":
        violation = _protection_violation(body or {}, bots)
        if violation:
            raise SafetyCheckError(f"branch '{default_branch}' is protected but {violation}")
        con.say(f"branch protection on '{default_branch}': ok")
        return

    # state == "missing": the branch has no protection yet.
    if handled_externally:
        con.say(f"branch '{default_branch}' is unprotected; "
                "--branch-protection-handled-externally was passed, skipping")
        return

    if not con.mutation(f"apply baseline branch protection to '{default_branch}'"):
        return
    try:
        gh.api(f"repos/{repo.slug}/branches/{default_branch}/protection",
               method="PUT", input_json=json.dumps(BASELINE_PROTECTION))
    except gh.GhError as exc:
        raise SafetyCheckError(
            f"branch '{default_branch}' is unprotected and the baseline "
            f"could not be applied: {exc}"
        ) from exc
    con.say(f"branch protection on '{default_branch}': created")


def _create_metrics_branch(repo: gh.Repo) -> None:
    """A parentless commit adding an empty metrics.jsonl, pushed as the
    `metrics` branch -- built through the Git Data API since `gh` has no
    plumbing for orphan commits."""
    blob_sha = gh.create_blob(repo.slug, "")
    tree_sha = gh.create_tree(repo.slug, [
        {"path": METRICS_FILE, "mode": "100644", "type": "blob", "sha": blob_sha},
    ])
    commit_sha = gh.create_commit(
        repo.slug, "chore(metrics): initialize metrics branch", tree_sha, parents=[])
    gh.create_branch(repo.slug, METRICS_BRANCH, commit_sha)


def check_metrics_branch(con: Console, repo: gh.Repo) -> None:
    con.step(f"Metrics branch: {METRICS_BRANCH}")

    if gh.ref_exists(repo.slug, METRICS_BRANCH):
        con.say(f"branch '{METRICS_BRANCH}': already exists")
    else:
        if not con.mutation(f"create orphan branch '{METRICS_BRANCH}' with empty {METRICS_FILE}"):
            return
        try:
            _create_metrics_branch(repo)
        except gh.GhError as exc:
            raise SafetyCheckError(f"could not create '{METRICS_BRANCH}': {exc}") from exc
        con.say(f"branch '{METRICS_BRANCH}': created")

    state, _ = gh.api_status(f"repos/{repo.slug}/branches/{METRICS_BRANCH}/protection")

    if state == "blocked":
        raise SafetyCheckError(
            f"can't read branch protection for '{METRICS_BRANCH}' -- "
            "your `gh` session needs admin access to this repo"
        )
    if state == "ok":
        con.say(f"branch protection on '{METRICS_BRANCH}': ok")
        return

    # state == "missing": the branch has no protection yet.
    if not con.mutation(f"apply deletion protection to '{METRICS_BRANCH}'"):
        return
    try:
        gh.api(f"repos/{repo.slug}/branches/{METRICS_BRANCH}/protection",
               method="PUT", input_json=json.dumps(METRICS_PROTECTION))
    except gh.GhError as exc:
        raise SafetyCheckError(
            f"branch '{METRICS_BRANCH}' is unprotected and could not be protected: {exc}"
        ) from exc
    con.say(f"branch protection on '{METRICS_BRANCH}': created")


def check_pages(con: Console, repo: gh.Repo) -> None:
    con.step("GitHub Pages")

    state, _ = gh.api_status(f"repos/{repo.slug}/pages")

    if state == "blocked":
        raise SafetyCheckError(
            "can't read GitHub Pages state -- your `gh` session needs admin access to this repo"
        )
    if state == "ok":
        con.say("GitHub Pages: enabled")
        return

    # state == "missing": Pages is off.
    if not con.mutation("enable GitHub Pages (GitHub Actions build type)"):
        return
    try:
        gh.api(f"repos/{repo.slug}/pages", method="POST", fields={"build_type": "workflow"})
    except gh.GhError as exc:
        raise SafetyCheckError(f"GitHub Pages could not be enabled: {exc}") from exc
    con.say("GitHub Pages: enabled")
