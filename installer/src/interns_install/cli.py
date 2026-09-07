"""`interns-install` — the interactive local half of interns setup.

Covers what a headless `install.yml` run cannot: minting the two bot GitHub
Apps (an interactive browser click), writing repo secrets/variables
(`secrets: write` is not grantable to `GITHUB_TOKEN`), and the branch
protection / Pages safety checks (reading or writing either needs admin
access, also not grantable to `GITHUB_TOKEN`). All of it runs with the
operator's own admin-scoped `gh` session, so no admin-capable token has to be
stored in the repo.

The caller-stub PR is opened here too: it adds files under
`.github/workflows/`, which `GITHUB_TOKEN` cannot push, so `install.yml` could
never open it (see #74). `install.yml` is left with just label sync and the
best-effort secret check, both fine under `github.token`.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import webbrowser

from . import gh, safety
from .apps import (
    APPS,
    AppSpec,
    ManifestServer,
    build_manifest,
    settings_app_url,
    settings_new_url,
)
from .console import Console

WORKFLOW = "install.yml"
INTERNS_REPO = "abi83/interns"

# Ref to copy the install wrapper from. install.sh exports INTERNS_REF; the
# default matches the pin baked into the templates.
INTERNS_REF = os.environ.get("INTERNS_REF") or "v0.1.0"

# Templates leave the interns ref as this placeholder so the pin always tracks
# the installer version -- both in the `uses:` line and in each wrapper's
# `ref:` fallback (never the consumer's commit SHA, see #73).
REF_PLACEHOLDER = "__INTERNS_REF__"

# Files interns-install stages into the consumer repo, source path in
# INTERNS_REPO -> destination path in the consumer. GITHUB_TOKEN cannot push
# .github/workflows/*, so install.yml can't add these itself (see #74) --
# interns-install commits them with the operator's own workflow-scoped session.
INSTALL_FILES = {
    f"templates/workflows/{WORKFLOW}": f".github/workflows/{WORKFLOW}",
    "templates/workflows/issue-pipeline.yml": ".github/workflows/issue-pipeline.yml",
    "templates/workflows/code-pipeline.yml": ".github/workflows/code-pipeline.yml",
    "templates/config/interns.yml": ".github/interns.yml",
}

INSTALL_PR_BODY = """\
## Install the interns pipeline

`interns-install` opened this PR to add the files a consumer repo needs before
the pipeline can run — `GITHUB_TOKEN` can't push `.github/workflows/*`, so the
workflow can't add them itself.

- **`.github/workflows/install.yml`** — thin `workflow_dispatch` caller for the
  reusable install workflow (label sync + secret checks).
- **`.github/workflows/{issue,code}-pipeline.yml`** — caller stubs that own the
  triggers and delegate to the reusable cores in `abi83/interns`, pinned to a
  release tag.
- **`.github/interns.yml`** — per-agent limits; every key is optional and falls
  back to the interns default.

Only missing files are added — an existing one is left untouched. After merging,
re-run `interns-install` (or dispatch **Install interns** from the Actions tab)
to sync the label manifest.
"""


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="interns-install",
        description="Provision a repo for the interns pipeline (bot identities + secrets).",
    )
    p.add_argument("--repo", metavar="OWNER/NAME",
                   help="target repo (default: the repo `gh` resolves for the cwd)")
    p.add_argument("--yes", action="store_true",
                   help="assume yes for every prompt (non-interactive)")
    p.add_argument("--coder-app-id", metavar="ID",
                   help="reuse the coder App with this ID instead of minting one "
                        "(the App is account-wide; only its install + secrets are per-repo)")
    p.add_argument("--reviewer-app-id", metavar="ID",
                   help="reuse the reviewer App with this ID instead of minting one")
    p.add_argument("--dry-run", action="store_true",
                   help="print every mutation without performing it")
    p.add_argument("--issue-templates", nargs="?", const="true", default="false",
                   metavar="true|false",
                   help="also stage the default issue templates when the repo has none")
    p.add_argument("--handoff-ref", metavar="REF",
                   help="ref to dispatch install.yml on (default: target default branch)")
    p.add_argument("--skip-handoff", action="store_true",
                   help="don't dispatch or describe install.yml")
    p.add_argument("--branch-protection-handled-externally", action="store_true",
                   help="skip applying baseline branch protection when unprotected -- "
                        "only if it's already enforced some other way (e.g. an org ruleset) "
                        "that this check can't see")
    return p.parse_args(argv)


def _scope_preflight(con: Console, repo: str) -> list[str] | None:
    existing = gh.list_secret_names(repo)
    if existing is None:
        con.warn(
            "your token can't list repo secrets — it is probably too narrow to "
            "write them either. Re-auth with `gh auth login -s repo` (classic) "
            "or a fine-grained PAT with Secrets: write, then re-run."
        )
        if not con.confirm("Continue anyway?", default=False):
            sys.exit(1)
    return existing


def _secret_verb(name: str, existing: list[str] | None) -> str:
    if existing is None:
        return "set"
    return "overwrite" if name in existing else "add"


def _app_owner(app: dict) -> str:
    """Login of the account that owns a `GET /apps/{slug}` result, lowercased.
    A same-name App owned by someone else is a global-namespace collision, not
    something this account can reuse."""
    return str((app.get("owner") or {}).get("login", "")).lower()


def _use_existing_app(con: Console, repo: gh.Repo, spec: AppSpec,
                      app_id: str | None, slug: str,
                      existing_secrets: list[str] | None) -> None:
    """Reuse an account-wide App: write this repo's App-ID variable and private
    key secret, and prompt to install it here. Never mints, never reads a key
    back — the operator pastes a PEM (reused from another repo, or freshly
    generated on the App's settings page; adding a key does not revoke others).
    """
    settings_url = settings_app_url(repo.owner, repo.is_org, slug)
    have_key = existing_secrets is not None and spec.key_secret in existing_secrets

    if con.dry_run:
        con.say(f"existing {spec.key} App — {settings_url}")
        con.mutation(f"set variable {spec.id_var} (existing {spec.key} App)")
        if not have_key:
            con.mutation(f"{_secret_verb(spec.key_secret, existing_secrets)} "
                         f"secret {spec.key_secret} (pasted PEM)")
        con.note_manual(f"install the existing {spec.key} App on {repo.slug}")
        return

    if app_id is None:
        con.say(f"its App ID (and 'Generate a private key') is on: {settings_url}")
        if con.assume_yes:
            con.note_manual(f"pass --{spec.key}-app-id (from {settings_url}) and set "
                            f"{spec.key_secret}, then install the App on {repo.slug}")
            return
        app_id = con.prompt(f"{spec.id_var} — the numeric App ID (blank to skip):")
        if not app_id:
            con.note_manual(f"set {spec.id_var} / {spec.key_secret} for the existing "
                            f"{spec.key} App, then install it on {repo.slug}")
            return
    else:
        con.say(f"reusing {spec.key} App {app_id} — {settings_url}")

    if con.mutation(f"set variable {spec.id_var} = {app_id}"):
        gh.set_variable(repo.slug, spec.id_var, app_id)

    if have_key:
        con.say(f"{spec.key_secret} is already set — leaving it (its key stays valid; "
                "keys held by other repos are unaffected)")
    elif con.assume_yes:
        con.note_manual(f"set the {spec.key_secret} secret (a PEM private key for "
                        f"'{slug}')")
    else:
        pem = con.prompt_secret(
            f"Paste a private key (PEM) for the '{slug}' App. This repo needs its "
            f"own copy in {spec.key_secret}; GitHub Actions secrets aren't shared "
            f"between repos. Reuse a .pem you saved for another repo, or generate "
            f"one at {settings_url}. Blank to set the secret yourself later:")
        if pem and con.mutation(
                f"{_secret_verb(spec.key_secret, existing_secrets)} secret {spec.key_secret}"):
            gh.set_secret(repo.slug, spec.key_secret, pem)
        elif not pem:
            con.note_manual(f"set the {spec.key_secret} secret (PEM private key)")
        pem = None  # noqa: F841 - drop the only reference to the key

    con.note_manual(
        f"confirm the {spec.key} App is installed on {repo.slug}: "
        f"https://github.com/apps/{slug}/installations/new"
    )


def _provision_app(con: Console, repo: gh.Repo, spec: AppSpec,
                   app_id: str | None,
                   existing_secrets: list[str] | None,
                   existing_vars: list[str] | None) -> None:
    name = spec.name_for(repo.owner)
    con.step(f"GitHub App: {name} ({spec.key})")

    if app_id is not None:
        con.say(f"--{spec.key}-app-id given — reusing App {app_id}, skipping the mint")
        _use_existing_app(con, repo, spec, app_id, name, existing_secrets)
        return

    if not con.confirm(f"Set up the App '{name}' now?", default=True):
        con.note_manual(f"create the {spec.key} App and set {spec.id_var} / {spec.key_secret}")
        return

    existing = gh.app_public(name)
    if existing and _app_owner(existing) == repo.owner.lower():
        con.say(f"you already own an App named '{name}' — reusing it, no duplicate minted")
        discovered_id = existing.get("id")
        _use_existing_app(con, repo, spec,
                          str(discovered_id) if discovered_id else None,
                          existing.get("slug", name), existing_secrets)
        return
    if existing:
        con.say(f"the name '{name}' is held by another account — GitHub will ask "
                "you to pick a different name in the form")

    action_url = settings_new_url(repo.owner, repo.is_org)

    if con.dry_run:
        con.mutation(f"open {action_url} to create App '{name}' via manifest")
        con.mutation(f"{_secret_verb(spec.key_secret, existing_secrets)} secret {spec.key_secret}")
        con.mutation(f"set variable {spec.id_var}")
        con.note_manual(f"install the {spec.key} App on {repo.slug}")
        return

    with ManifestServer(action_url, lambda redirect: build_manifest(
        name, redirect, spec.description)) as server:
        con.say(f"opening your browser to create '{name}' — "
                "click 'Create GitHub App'")
        con.say(f"if nothing opened, visit: {server.base_url}")
        webbrowser.open(server.base_url)
        code = server.wait_for_code()

    conv = gh.convert_manifest(code)
    app_id = str(conv["id"])
    slug = conv.get("slug", name)
    pem = conv["pem"]

    # Resilient ordering: the private key is returned exactly once, so it goes
    # straight into the secret before we do anything else.
    if con.mutation(f"{_secret_verb(spec.key_secret, existing_secrets)} secret {spec.key_secret}"):
        gh.set_secret(repo.slug, spec.key_secret, pem)
    pem = None  # noqa: F841 - drop the only reference to the key

    if con.mutation(f"set variable {spec.id_var} = {app_id}"):
        gh.set_variable(repo.slug, spec.id_var, app_id)

    con.say(f"App '{slug}' created (id {app_id})")
    con.note_manual(
        f"install the {spec.key} App on {repo.slug}: "
        f"https://github.com/apps/{slug}/installations/new"
    )


def _write_oauth_token(con: Console, repo: gh.Repo, existing_secrets: list[str] | None) -> None:
    con.step("Claude Code OAuth token")
    if con.dry_run:
        con.mutation(f"{_secret_verb('CLAUDE_CODE_OAUTH_TOKEN', existing_secrets)} "
                     "secret CLAUDE_CODE_OAUTH_TOKEN")
        return
    token = con.prompt_secret("Paste the CLAUDE_CODE_OAUTH_TOKEN (leave blank to skip):")
    if not token:
        con.note_manual("set the CLAUDE_CODE_OAUTH_TOKEN secret")
        return
    if con.mutation(f"{_secret_verb('CLAUDE_CODE_OAUTH_TOKEN', existing_secrets)} "
                    "secret CLAUDE_CODE_OAUTH_TOKEN"):
        gh.set_secret(repo.slug, "CLAUDE_CODE_OAUTH_TOKEN", token)


def _handoff(con: Console, repo: gh.Repo, args: argparse.Namespace) -> None:
    con.step("Hand off to install.yml (label sync + secret checks)")

    base = _default_branch(repo)
    pr_url = _stage_install_files(con, repo, base, args.issue_templates == "true")
    if pr_url is not None:
        con.note_manual(
            f"merge {pr_url}, then re-run interns-install (or dispatch {WORKFLOW} "
            f"from the Actions tab) to sync the label manifest"
        )
        return

    ref = args.handoff_ref or base
    if not con.confirm(f"Dispatch {WORKFLOW} on {repo.slug}@{ref} now?", default=True):
        con.note_manual(f"run `gh workflow run {WORKFLOW} --repo {repo.slug} --ref {ref}`")
        return
    if con.mutation(f"dispatch {WORKFLOW} on {repo.slug}@{ref}"):
        gh.dispatch_workflow(repo.slug, WORKFLOW, ref, {})


def _collect_missing_files(repo: gh.Repo, base: str, issue_templates: bool) -> dict[str, str]:
    """Destination path -> file content, for every interns install file not
    already present on `base`. Reads template content from INTERNS_REPO."""
    wanted: dict[str, str] = {}
    for src, dest in INSTALL_FILES.items():
        if not gh.path_exists(repo.slug, dest, base):
            content = gh.get_file(INTERNS_REPO, src, INTERNS_REF)
            wanted[dest] = content.replace(REF_PLACEHOLDER, INTERNS_REF)

    if issue_templates and not gh.path_exists(repo.slug, ".github/ISSUE_TEMPLATE", base):
        for name in gh.list_dir(INTERNS_REPO, "templates/issue", INTERNS_REF):
            wanted[f".github/ISSUE_TEMPLATE/{name}"] = gh.get_file(
                INTERNS_REPO, f"templates/issue/{name}", INTERNS_REF)
    return wanted


def _stage_install_files(con: Console, repo: gh.Repo, base: str,
                         issue_templates: bool) -> str | None:
    """Open one PR adding whichever interns install files are missing from the
    consumer repo. Returns the PR URL, or None when nothing was missing."""
    if con.dry_run:
        con.mutation(f"open a PR adding any missing interns install files to {repo.slug}")
        con.note_manual(f"merge the interns install PR, then re-run interns-install")
        return "(dry-run)"

    wanted = _collect_missing_files(repo, base, issue_templates)
    if not wanted:
        con.say("all interns install files already present")
        return None

    con.say("missing: " + ", ".join(sorted(wanted)))
    if not con.confirm(f"Open a PR adding {len(wanted)} file(s) to {repo.slug}?", default=True):
        con.note_manual(
            "add the missing files listed above by hand, then re-run interns-install"
        )
        return None

    branch = f"interns/install-{int(time.time())}"
    sha = gh.branch_head_sha(repo.slug, base)
    con.mutation(f"open a PR on {repo.slug} adding: {', '.join(sorted(wanted))}")
    gh.create_branch(repo.slug, branch, sha)
    for dest, content in wanted.items():
        gh.put_file(repo.slug, dest, content,
                    "chore: install interns pipeline caller stubs", branch)
    url = gh.create_pr(repo.slug, branch, base,
                       "Install the interns pipeline", INSTALL_PR_BODY)
    con.say(f"opened {url}")
    return url


def _default_branch(repo: gh.Repo) -> str:
    data = gh.api(f"repos/{repo.slug}")
    return data.get("default_branch", "main") if isinstance(data, dict) else "main"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    con = Console(assume_yes=args.yes, dry_run=args.dry_run)

    try:
        gh.ensure_available()
        repo = gh.current_repo(args.repo)
    except gh.GhError as exc:
        con.error(str(exc))
        return 1

    con.say(f"target repo: {repo.slug}" + (" (dry run)" if args.dry_run else ""))

    existing_secrets = _scope_preflight(con, repo.slug)
    existing_vars = gh.list_variable_names(repo.slug)

    try:
        default_branch = _default_branch(repo)
        safety.check_branch_protection(con, repo, default_branch,
                                        handled_externally=args.branch_protection_handled_externally)
        safety.check_pages(con, repo)
    except (gh.GhError, safety.SafetyCheckError) as exc:
        con.error(str(exc))
        con.summary()
        return 1

    try:
        app_ids = {"coder": args.coder_app_id, "reviewer": args.reviewer_app_id}
        for spec in APPS:
            _provision_app(con, repo, spec, app_ids.get(spec.key),
                           existing_secrets, existing_vars)
        _write_oauth_token(con, repo, existing_secrets)
        if not args.skip_handoff:
            _handoff(con, repo, args)
    except (gh.GhError, TimeoutError) as exc:
        con.error(str(exc))
        con.summary()
        return 1

    con.summary()
    return 0
