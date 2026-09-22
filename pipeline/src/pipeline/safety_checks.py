"""Best-effort presence check for the pipeline's secrets and Actions
variables (reviewer, coder *and* triage GitHub App identities). Their
values can't be set from here, so a definitively missing one is a hard
failure with instructions; if the token can't even list them, that's a
warning, not a failure, since GITHUB_TOKEN is never granted the scope to
list secrets.

Branch protection and GitHub Pages need admin access GITHUB_TOKEN never
has -- interns-install checks and fixes those locally instead (see
installer/src/interns_install/safety.py).
"""

from __future__ import annotations

import os
import sys

from . import best_effort, gh
from .ctx import ActionsCtx

DEFAULT_REQUIRED_SECRETS = [
    "CLAUDE_CODE_OAUTH_TOKEN",
    "INTERNS_REVIEWER_APP_PRIVATE_KEY",
    "INTERNS_CODER_APP_PRIVATE_KEY",
    "INTERNS_TRIAGE_APP_PRIVATE_KEY",
]
DEFAULT_REQUIRED_VARS = [
    "INTERNS_REVIEWER_CLIENT_ID",
    "INTERNS_CODER_CLIENT_ID",
    "INTERNS_TRIAGE_CLIENT_ID",
]


def check_secrets(repo: str, required: list[str]) -> list[str]:
    """Returns failure message(s) -- empty when required secrets are all
    present, or when they can't be listed (a printed warning, not a failure)."""
    existing = best_effort.call(
        f"token lacks secrets read scope; verify {' '.join(required)} manually",
        gh.GhCommandError,
        gh.list_secret_names,
        repo,
    )
    if existing is None:
        return []
    missing = [name for name in required if name not in existing]
    if missing:
        msg = (f"missing repo secret(s): {' '.join(missing)} "
               "-- add them under Settings > Secrets and variables > Actions")
        print(f"safety-checks: FAIL: {msg}", file=sys.stderr)
        return [msg]
    print(f"safety-checks: required secrets present: {' '.join(required)}")
    return []


def check_vars(repo: str, required: list[str]) -> list[str]:
    """Same as check_secrets, for Actions variables."""
    existing = best_effort.call(
        f"token lacks variables read scope; verify {' '.join(required)} manually",
        gh.GhCommandError,
        gh.list_variable_names,
        repo,
    )
    if existing is None:
        return []
    missing = [name for name in required if name not in existing]
    if missing:
        msg = (f"missing repo variable(s): {' '.join(missing)} "
               "-- add them under Settings > Secrets and variables > Actions")
        print(f"safety-checks: FAIL: {msg}", file=sys.stderr)
        return [msg]
    print(f"safety-checks: required variables present: {' '.join(required)}")
    return []


def _main(ctx: ActionsCtx) -> int:
    required_secrets = os.environ.get("REQUIRED_SECRETS", " ".join(DEFAULT_REQUIRED_SECRETS)).split()
    required_vars = os.environ.get("REQUIRED_VARS", " ".join(DEFAULT_REQUIRED_VARS)).split()

    failures = check_secrets(ctx.repo, required_secrets) + check_vars(ctx.repo, required_vars)

    if failures:
        print(file=sys.stderr)
        print(f"safety-checks: {len(failures)} safety check(s) failed -- install aborted", file=sys.stderr)
        return 1
    print("safety-checks: all safety checks passed")
    return 0
