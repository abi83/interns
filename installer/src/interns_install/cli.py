"""`interns-install` — the interactive local half of interns setup.

Covers what a headless `install.yml` run cannot: minting the two bot GitHub
Apps (an interactive browser click), writing repo secrets/variables
(`secrets: write` is not grantable to `GITHUB_TOKEN`), and the branch
protection / Pages safety checks (reading or writing either needs admin
access, also not grantable to `GITHUB_TOKEN`). All of it runs with the
operator's own admin-scoped `gh` session, so no admin-capable token has to be
stored in the repo. Everything else -- label sync, the caller-stub PR -- is
handed off to `install.yml`.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from . import gh, safety
from .apps import APPS, AppSpec, ManifestServer, build_manifest, settings_new_url
from .console import Console

WORKFLOW = "install.yml"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="interns-install",
        description="Provision a repo for the interns pipeline (bot identities + secrets).",
    )
    p.add_argument("--repo", metavar="OWNER/NAME",
                   help="target repo (default: the repo `gh` resolves for the cwd)")
    p.add_argument("--yes", action="store_true",
                   help="assume yes for every prompt (non-interactive)")
    p.add_argument("--dry-run", action="store_true",
                   help="print every mutation without performing it")
    p.add_argument("--issue-templates", nargs="?", const="true", default="false",
                   metavar="true|false",
                   help="tell install.yml to add the default issue templates")
    p.add_argument("--handoff-ref", metavar="REF",
                   help="ref to dispatch install.yml on (default: target default branch)")
    p.add_argument("--skip-handoff", action="store_true",
                   help="don't dispatch or describe install.yml")
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


def _provision_app(con: Console, repo: gh.Repo, spec: AppSpec,
                   existing_secrets: list[str] | None,
                   existing_vars: list[str] | None) -> None:
    con.step(f"GitHub App: {spec.default_name} ({spec.key})")
    if not con.confirm(f"Create the App '{spec.default_name}' now?", default=True):
        con.note_manual(f"create the {spec.key} App and set {spec.id_var} / {spec.key_secret}")
        return

    action_url = settings_new_url(repo.owner, repo.is_org)

    if con.dry_run:
        con.mutation(f"open {action_url} to create App '{spec.default_name}' via manifest")
        con.mutation(f"{_secret_verb(spec.key_secret, existing_secrets)} secret {spec.key_secret}")
        con.mutation(f"set variable {spec.id_var}")
        con.note_manual(f"install the {spec.key} App on {repo.slug}")
        return

    with ManifestServer(action_url, lambda redirect: build_manifest(
        spec.default_name, redirect, spec.description)) as server:
        con.say(f"opening your browser to create '{spec.default_name}' — "
                "click 'Create GitHub App' (rename it first if that name is taken)")
        con.say(f"if nothing opened, visit: {server.base_url}")
        webbrowser.open(server.base_url)
        code = server.wait_for_code()

    conv = gh.convert_manifest(code)
    app_id = str(conv["id"])
    slug = conv.get("slug", spec.default_name)
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
    con.step("Hand off to install.yml (labels, caller stubs, safety checks)")
    inputs = {"install_issue_templates": args.issue_templates}

    if not gh.workflow_exists(repo.slug, WORKFLOW):
        con.note_manual(
            f"add a thin wrapper that calls abi83/interns/.github/workflows/{WORKFLOW} "
            f"(see the interns README), then run it — or `gh workflow run {WORKFLOW} "
            f"--repo {repo.slug}` once present"
        )
        con.say(f"{WORKFLOW} is not in {repo.slug} yet — see the summary for the manual step")
        return

    ref = args.handoff_ref or _default_branch(repo)
    if not con.confirm(f"Dispatch {WORKFLOW} on {repo.slug}@{ref} now?", default=True):
        con.note_manual(f"run `gh workflow run {WORKFLOW} --repo {repo.slug} --ref {ref}`")
        return
    if con.mutation(f"dispatch {WORKFLOW} on {repo.slug}@{ref}"):
        gh.dispatch_workflow(repo.slug, WORKFLOW, ref, inputs)


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
                                        config_path=Path(".github/interns.yml"))
        safety.check_pages(con, repo)
    except (gh.GhError, safety.SafetyCheckError) as exc:
        con.error(str(exc))
        con.summary()
        return 1

    try:
        for spec in APPS:
            _provision_app(con, repo, spec, existing_secrets, existing_vars)
        _write_oauth_token(con, repo, existing_secrets)
        if not args.skip_handoff:
            _handoff(con, repo, args)
    except (gh.GhError, TimeoutError) as exc:
        con.error(str(exc))
        con.summary()
        return 1

    con.summary()
    return 0
