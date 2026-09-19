"""GitHub App permission matrices and manifest-flow data helpers.

Building and serving the manifest form itself lives in `manifest_server.py`
-- this module stays a pure data module (App specs, permission matrices,
manifest/URL building) with no server or I/O.

https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest
"""

from __future__ import annotations

from dataclasses import dataclass

# Permission matrix is fixed by the pipeline's needs (see README / #10):
# push branches, open and review PRs, edit issues and labels, read check runs.
APP_PERMISSIONS = {
    "contents": "write",
    "pull_requests": "write",
    "issues": "write",
    "checks": "read",
    "metadata": "read",
}

# The triage App only ever edits issue labels (see #89) -- no repo contents or
# PR access needed.
TRIAGE_APP_PERMISSIONS = {
    "issues": "write",
    "metadata": "read",
}


@dataclass
class AppSpec:
    key: str            # "reviewer" / "coder" / "triage"
    name_base: str      # "interns-reviewer" / "interns-coder" / "interns-triage"
    client_id_var: str  # "INTERNS_REVIEWER_CLIENT_ID"
    key_secret: str     # "INTERNS_REVIEWER_APP_PRIVATE_KEY"
    description: str
    permissions: dict[str, str] | None = None  # None = APP_PERMISSIONS

    def name_for(self, owner: str) -> str:
        """GitHub App names are globally unique, so the minted name carries the
        owning account: two accounts each get their own `interns-<role>-<acct>`
        instead of racing for one global `interns-<role>`."""
        return f"{self.name_base}-{owner.lower()}"


APPS = [
    AppSpec(
        key="reviewer",
        name_base="interns-reviewer",
        client_id_var="INTERNS_REVIEWER_CLIENT_ID",
        key_secret="INTERNS_REVIEWER_APP_PRIVATE_KEY",
        description="submits PR reviews for the interns pipeline (claude[bot] can't approve its own PR)",
    ),
    AppSpec(
        key="coder",
        name_base="interns-coder",
        client_id_var="INTERNS_CODER_CLIENT_ID",
        key_secret="INTERNS_CODER_APP_PRIVATE_KEY",
        description="coder-side pushes, PRs, comments and label edits for the interns pipeline",
    ),
    AppSpec(
        key="triage",
        name_base="interns-triage",
        client_id_var="INTERNS_TRIAGE_CLIENT_ID",
        key_secret="INTERNS_TRIAGE_APP_PRIVATE_KEY",
        description="applies status:refined so the estimate phase actually triggers "
                     "(GITHUB_TOKEN-authored label edits never fire new workflow runs)",
        permissions=TRIAGE_APP_PERMISSIONS,
    ),
]


def build_manifest(name: str, repo_slug: str, redirect_url: str, description: str,
                    permissions: dict[str, str] | None = None) -> dict:
    return {
        "name": name,
        "url": f"https://github.com/{repo_slug}",
        "description": description,
        "redirect_url": redirect_url,
        "public": False,
        "default_events": [],
        "default_permissions": permissions or APP_PERMISSIONS,
    }


def settings_new_url(repo_owner: str, is_org: bool) -> str:
    if is_org:
        return f"https://github.com/organizations/{repo_owner}/settings/apps/new"
    return "https://github.com/settings/apps/new"


def settings_app_url(repo_owner: str, is_org: bool, slug: str) -> str:
    """Settings page of an existing App — where its App ID is shown and a new
    private key can be generated."""
    if is_org:
        return f"https://github.com/organizations/{repo_owner}/settings/apps/{slug}"
    return f"https://github.com/settings/apps/{slug}"
