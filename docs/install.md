# Install

How to set interns up in a repo. Run it from a local clone, with the
[GitHub CLI](https://cli.github.com/) authenticated (`gh auth login`) as an account with
**admin access to the repo**: the installer creates secrets, variables and branch protection.

```bash
curl -LsSf https://raw.githubusercontent.com/abi83/interns/v0/install.sh | sh
```

The script installs [`uv`](https://docs.astral.sh/uv/) if missing, then runs `interns-install`
([`installer/`](../installer/README.md)). On a fresh repo it opens one PR with the workflow files and starter config;
merge it and re-run the installer once. The re-run dispatches `install.yml`, which only syncs
labels, and that workflow exists on the default branch only after the merge.
The installer is idempotent: re-run any time to fix drift. `interns-install --help` lists every flag.

TODO: sync labels from the installer and drop the re-run: [#365](https://github.com/abi83/interns/issues/365).

The installer runs locally, not in Actions, because `GITHUB_TOKEN` is never granted admin
access or `secrets: write`.

Prerequisite for the workflows: the [`yq`](https://github.com/mikefarah/yq) binary on `PATH`.
GitHub-hosted runners have it; self-hosted runners must provide it.

## What the installer does

| # | Step | Why |
|---|---|---|
| 1 | Check (and fix) default-branch protection | Every agent change must go through a PR. |
| 2 | Check (and enable) GitHub Pages | Deploy target for the dashboard. |
| 3 | Check (and create) the `metrics` branch | Orphan branch the pipeline appends run metrics to. |
| 4 | Mint (or reuse) three GitHub Apps | See [GitHub Apps](#github-apps). |
| 5 | Write App secrets and variables, plus `CLAUDE_CODE_OAUTH_TOKEN` | The workflows authenticate as the Apps and call Claude. |
| 6 | Open the install PR | Adds the workflow files and starter config if missing or drifted. Merge it, then re-run. |
| 7 | Dispatch `install.yml` | Once nothing is left to add, the installer runs the workflow for you. |
| 8 | `install.yml`: sync labels | The pipeline routes on labels ([`.github/labels.json`](../.github/labels.json)). |

The PR in step 6 writes under `.github/workflows/`, so a classic `gh` token needs the
`workflow` scope. The installer checks for it up front.

## Default-branch protection

No pipeline identity (`github-actions[bot]` or the three Apps) may be on the default
branch's push allowlist.

| Default branch | Result |
|---|---|
| requires a PR review, no bot on the allowlist | passes |
| unprotected | installer applies the baseline: PR + 1 approval, no force-push, no deletion |
| protected, but your `gh` session lacks admin | **fails**: re-auth with admin, re-run |
| a bot identity is on the allowlist | **fails**: remove it, re-run |

If an org-wide ruleset (or similar) enforces protection where the check can't see it, pass
`--branch-protection-handled-externally`.

## GitHub Apps

Three Apps, `interns-{coder,reviewer,triage}-<owner>`, each minted with one "Create GitHub App"
click (App Manifest flow). You then install each on the repo; the installer prints the links.

- **Coder and reviewer** are separate identities so the reviewer can approve the coder's PRs.
- **Triage** applies labels that must start the next job. Label edits by `GITHUB_TOKEN`
  never trigger new runs.

Permissions are fixed in [`apps.py`](../installer/src/interns_install/apps.py): coder and
reviewer get Contents, Pull requests and Issues (read and write), Checks and Metadata (read);
triage gets only Issues (read and write) and Metadata (read). No webhooks.

**One App, many repos.** Apps belong to an account; only the installation and the secrets are
per repo. For a second repo under the same account, reuse the Apps: pass
`--{coder,reviewer,triage}-client-id`, or answer the installer's prompt. For the key, paste
the PEM the first repo stores or generate another (extra keys don't revoke the others). Then
install the App on the new repo.

## Secrets and variables

Written by the installer. For `CLAUDE_CODE_OAUTH_TOKEN`, run `claude setup-token` locally
(Claude Pro or Max).

| Kind | Name |
|---|---|
| Secret | `CLAUDE_CODE_OAUTH_TOKEN` |
| Secret | `INTERNS_{CODER,REVIEWER,TRIAGE}_APP_PRIVATE_KEY` |
| Variable | `INTERNS_{CODER,REVIEWER,TRIAGE}_CLIENT_ID` |

A missing one fails the pipeline with a clear error on first use.

## The install PR

The installer opens one PR, committed with your own `gh` session (which has the `workflow`
scope that `GITHUB_TOKEN` never gets), adding:

- [`install.yml`](../templates/workflows/install.yml): a thin wrapper for the reusable install workflow.
- [`issue-pipeline.yml` and `code-pipeline.yml`](../templates/workflows): caller stubs that own
  the triggers and delegate to the reusable workflows.
- `.github/interns.yml`: starter config with every key commented out, rendered from
  [`defaults.yml`](../templates/config/defaults.yml). Added only if absent.
- `Makefile` with `setup` / `test` / `build` stubs (the `setup` stub is appended to an existing Makefile that lacks it).
- `interns-metrics/index.html`: the metrics dashboard page.

Missing files are added and the three workflow files are re-synced if they drifted.
Merge the PR, then re-run `interns-install`, which dispatches `install.yml` to sync labels.
`--issue-templates` also adds the default [issue templates](../templates/issue) when the repo
has none.

### Versions

The stubs pin `@v0`, a floating tag moved to every release, like `actions/checkout@v4`.
Minor and patch releases reach you with no edits; a breaking change would ship as `v1`.
For a reproducible pin use `vX.Y.Z`. `next` tracks `main` (internal testing; set
`INTERNS_REF=next` when installing). Releases are cut by
[release-please](https://github.com/googleapis/release-please) from conventional commits.

## Doing it by hand

Without `interns-install`: create the three Apps with the permissions above and install them,
add the secrets and variables, set branch protection, and commit the files from
[`templates/workflows/`](../templates/workflows) yourself. Then run `gh workflow run install.yml`
to sync labels. `.github/interns.yml` is optional; use only the keys you override, with
`defaults.yml` as the reference.
