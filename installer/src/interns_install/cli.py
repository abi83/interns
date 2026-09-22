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
import sys
import time

from interns import gh

from . import gh_admin, install_files, safety
from .apps import APPS, provision_app, request_install, secret_mutation, write_secret
from .console import Console

WORKFLOW = install_files.WORKFLOW


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="interns-install",
        description="Provision a repo for the interns pipeline (bot identities + secrets).",
    )
    p.add_argument("--repo", metavar="OWNER/NAME",
                   help="target repo (default: the repo `gh` resolves for the cwd)")
    p.add_argument("--yes", action="store_true",
                   help="assume yes for every prompt (non-interactive)")
    p.add_argument("--coder-client-id", metavar="ID",
                   help="reuse the coder App with this Client ID instead of minting one "
                        "(the App is account-wide; only its install + secrets are per-repo)")
    p.add_argument("--reviewer-client-id", metavar="ID",
                   help="reuse the reviewer App with this Client ID instead of minting one")
    p.add_argument("--triage-client-id", metavar="ID",
                   help="reuse the triage App with this Client ID instead of minting one")
    p.add_argument("--dry-run", action="store_true",
                   help="print every mutation without performing it")
    p.add_argument("--issue-templates", action="store_true",
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


def _workflow_scope_ok(con: Console) -> bool:
    """The handoff unconditionally writes `.github/workflows/install.yml`, which
    GitHub blocks (with an opaque 404) unless a classic token carries the
    `workflow` scope. `auth_scopes()` is empty for a fine-grained PAT, whose
    Workflows: write permission we can't see here -- fall through to the
    existing best-effort behaviour in that case."""
    scopes = gh_admin.auth_scopes()
    if not scopes or "workflow" in scopes:
        return True
    con.error(
        "your `gh` token is missing the `workflow` scope, required to add "
        "`.github/workflows/install.yml`. Run "
        "`gh auth refresh -h github.com -s workflow` (or regenerate the PAT "
        "with `workflow` checked) and re-run."
    )
    return False


def _secrets_scope_ok(con: Console, existing_secrets: list[str] | None) -> bool:
    if existing_secrets is not None:
        return True
    con.warn(
        "your token can't list repo secrets — it is probably too narrow to "
        "write them either. Re-auth with `gh auth login -s repo` (classic) "
        "or a fine-grained PAT with Secrets: write, then re-run."
    )
    return con.confirm("Continue anyway?", default=False)


def _write_oauth_token(con: Console, repo: gh_admin.Repo, existing_secrets: list[str] | None) -> None:
    con.step("Claude Code OAuth token")
    # Separate App from the interns-* ones above: without it installed, the
    # OAuth token exchange 401s and every coder/reviewer/refiner run fails.
    request_install(con, repo, "claude", "Claude Code GitHub App")

    if con.dry_run:
        secret_mutation(con, "CLAUDE_CODE_OAUTH_TOKEN", existing_secrets)
        return

    token = con.prompt_secret("Paste the CLAUDE_CODE_OAUTH_TOKEN (leave blank to skip):")
    if not token:
        con.note_manual("set the CLAUDE_CODE_OAUTH_TOKEN secret")
        return
    write_secret(con, repo, "CLAUDE_CODE_OAUTH_TOKEN", token, existing_secrets)


def _stage_install_files(con: Console, repo: gh_admin.Repo, base: str,
                         issue_templates: bool) -> str | None:
    """Open one PR adding missing files and re-syncing drifted ones. Returns
    the PR URL, or None when nothing needed changing."""
    if con.dry_run:
        con.mutation(f"open a PR adding/syncing any missing or stale interns install files to {repo.slug}")
        con.note_manual("merge the interns install PR, then re-run interns-install")
        return "(dry-run)"

    wanted = install_files.collect_missing_files(repo, base, issue_templates)
    if not wanted:
        con.say("all interns install files already present and up to date")
        return None

    added = sorted(dest for dest, (_, sha) in wanted.items() if sha is None)
    stale = sorted(dest for dest, (_, sha) in wanted.items() if sha is not None)
    if added:
        con.say("missing: " + ", ".join(added))
    if stale:
        con.say("out of date: " + ", ".join(stale))
    if not con.confirm(f"Open a PR adding/updating {len(wanted)} file(s) on {repo.slug}?", default=True):
        con.note_manual(
            "add/update the files listed above by hand, then re-run interns-install"
        )
        return None

    branch = f"interns/install-{int(time.time())}"
    base_sha = gh_admin.branch_head_sha(repo.slug, base)
    con.mutation(f"open a PR on {repo.slug} adding/updating: {', '.join(sorted(wanted))}")
    gh_admin.create_branch(repo.slug, branch, base_sha)
    for dest, (content, file_sha) in wanted.items():
        gh_admin.put_file(repo.slug, dest, content,
                    "chore: install interns pipeline caller stubs", branch,
                    sha=file_sha)
    url = gh.pr_create(repo.slug, branch, base,
                       "Install the interns pipeline", install_files.INSTALL_PR_BODY)
    con.say(f"opened {url}")
    return url


def _handoff(con: Console, repo: gh_admin.Repo, args: argparse.Namespace) -> None:
    con.step("Hand off to install.yml (label sync + secret checks)")

    base = gh.default_branch(repo.slug)
    pr_url = _stage_install_files(con, repo, base, args.issue_templates)
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


def _fatal(con: Console, exc: Exception, *, with_summary: bool) -> int:
    con.error(str(exc))
    if with_summary:
        con.summary()
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    con = Console(assume_yes=args.yes, dry_run=args.dry_run)

    try:
        gh_admin.ensure_available()
        repo = gh_admin.current_repo(args.repo)
    except gh.GhError as exc:
        return _fatal(con, exc, with_summary=False)

    con.say(f"target repo: {repo.slug}" + (" (dry run)" if args.dry_run else ""))

    if not args.skip_handoff and not _workflow_scope_ok(con):
        return 1
    try:
        existing_secrets = gh.list_secret_names(repo.slug)
    except gh.GhCommandError:
        existing_secrets = None
    if not _secrets_scope_ok(con, existing_secrets):
        return 1

    try:
        default_branch = gh.default_branch(repo.slug)
        safety.check_branch_protection(con, repo, default_branch,
                                        handled_externally=args.branch_protection_handled_externally)
        safety.check_pages(con, repo)
        safety.check_metrics_branch(con, repo)
    except (gh.GhError, safety.SafetyCheckError) as exc:
        return _fatal(con, exc, with_summary=True)

    try:
        client_ids = {"coder": args.coder_client_id, "reviewer": args.reviewer_client_id,
                      "triage": args.triage_client_id}
        for spec in APPS:
            provision_app(con, repo, spec, client_ids.get(spec.key), existing_secrets)
        _write_oauth_token(con, repo, existing_secrets)
        if not args.skip_handoff:
            _handoff(con, repo, args)
    except (gh.GhError, TimeoutError) as exc:
        return _fatal(con, exc, with_summary=True)

    con.summary()
    return 0
