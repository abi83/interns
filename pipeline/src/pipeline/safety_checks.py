"""Best-effort presence check for the pipeline's secrets and Actions
variables (reviewer, coder *and* triage GitHub App identities). Their
values can't be set from here, so a definitively missing one is a hard
failure with instructions; if the token can't even list them, that's a
warning, not a failure, since GITHUB_TOKEN is never granted the scope to
list secrets.

Branch protection and GitHub Pages need admin access GITHUB_TOKEN never
has -- interns-install checks and fixes those locally instead (see
installer/src/interns_install/safety.py).

safety-checks.sh is a thin shim over this module.
"""

from __future__ import annotations

import os
import sys

from . import gh

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
    existing = gh.list_secret_names(repo)
    if existing is None:
        print(f"safety-checks: WARNING: can't list repo secrets (token lacks the scope) "
              f"-- verify manually: {' '.join(required)}")
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
    existing = gh.list_variable_names(repo)
    if existing is None:
        print(f"safety-checks: WARNING: can't list repo variables (token lacks the scope) "
              f"-- verify manually: {' '.join(required)}")
        return []
    missing = [name for name in required if name not in existing]
    if missing:
        msg = (f"missing repo variable(s): {' '.join(missing)} "
               "-- add them under Settings > Secrets and variables > Actions")
        print(f"safety-checks: FAIL: {msg}", file=sys.stderr)
        return [msg]
    print(f"safety-checks: required variables present: {' '.join(required)}")
    return []


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"safety-checks: {name} unset")
    return value


def _main() -> int:
    repo = _require_env("GITHUB_REPOSITORY")
    _require_env("GH_TOKEN")

    required_secrets = os.environ.get("REQUIRED_SECRETS", " ".join(DEFAULT_REQUIRED_SECRETS)).split()
    required_vars = os.environ.get("REQUIRED_VARS", " ".join(DEFAULT_REQUIRED_VARS)).split()

    failures = check_secrets(repo, required_secrets) + check_vars(repo, required_vars)

    if failures:
        print(file=sys.stderr)
        print(f"safety-checks: {len(failures)} safety check(s) failed -- install aborted", file=sys.stderr)
        return 1
    print("safety-checks: all safety checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
