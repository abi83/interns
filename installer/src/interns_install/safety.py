"""Branch-protection and Pages safety checks.

These run locally, using the operator's own admin-scoped `gh` session -- the
same one interns-install already needs to mint Apps and write secrets.
Reading or writing branch protection and Pages state needs admin access to
the repo, which `GITHUB_TOKEN` can never be granted; running the checks here
instead of in a follow-up Actions workflow means no admin-capable token ever
has to be stashed as a repo secret.
"""

from __future__ import annotations

from pathlib import Path

from . import gh
from .console import Console

DEFAULT_BOT_LOGINS = ["github-actions[bot]", "claude[bot]"]

# Require a PR + 1 approval, no force pushes or deletions, no push restrictions.
BASELINE_PROTECTION = """\
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": { "required_approving_review_count": 1 },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false
}
"""


class SafetyCheckError(RuntimeError):
    pass


def _config_allows_agent_push(config_path: Path) -> bool:
    if not config_path.exists():
        return False
    for line in config_path.read_text().splitlines():
        key, _, value = line.partition("#")[0].partition(":")
        if key.strip() == "allow_agent_push_to_default_branch":
            return value.strip().lower() == "true"
    return False


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
                             config_path: Path,
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
    if _config_allows_agent_push(config_path):
        con.say(f"branch '{default_branch}' is unprotected; "
                "allow_agent_push_to_default_branch is set, skipping")
        return

    if not con.mutation(f"apply baseline branch protection to '{default_branch}'"):
        return
    try:
        gh.api(f"repos/{repo.slug}/branches/{default_branch}/protection",
               method="PUT", input_json=BASELINE_PROTECTION)
    except gh.GhError as exc:
        raise SafetyCheckError(
            f"branch '{default_branch}' is unprotected and the baseline "
            f"could not be applied: {exc}"
        ) from exc
    con.say(f"branch protection on '{default_branch}': created")


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
