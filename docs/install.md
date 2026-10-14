# Install

How to set interns up in a repo. Run it from a local clone, with the
[GitHub CLI](https://cli.github.com/) authenticated (`gh auth login`) as an account with
**admin access to the repo**: the installer creates secrets, variables and branch protection.

```bash
curl -LsSf https://raw.githubusercontent.com/abi83/interns/v0/install.sh | sh
```

The script installs [`uv`](https://docs.astral.sh/uv/) if missing, then runs `interns-install`
([`installer/`](../installer/README.md)). On a fresh repo it opens one PR with the workflow files and starter config;
merge it. Merging triggers `install.yml`, which syncs the labels.
The installer is idempotent: re-run it any time to fix drift. `interns-install --help` lists every flag.

**Why it runs on your machine.** The installer creates the three GitHub Apps (account-level, with
one browser click each), stores their keys and IDs as repo secrets and variables, and sets branch
protection and Pages. That takes admin rights. Nothing a workflow holds has them: `GITHUB_TOKEN` can't be granted admin or
`secrets: write`, and the pipeline's Apps are created without them. So the installer runs under your
own `gh` login, which must be a repo admin.

## What the installer does

| # | Step | Why |
|---|---|---|
| 1 | Check (and fix) default-branch protection | Every agent change must go through a PR. |
| 2 | Check (and enable) GitHub Pages | Serves the [metrics dashboard](metrics.md#dashboard), a static page charting the pipeline's cost, turns and results. |
| 3 | Check (and create) the `interns-metrics` branch | Orphan branch the pipeline appends [run metrics](metrics.md) to; the dashboard reads it. |
| 4 | Mint (or reuse) three GitHub Apps | See [GitHub Apps](#github-apps). |
| 5 | Write App secrets and variables, plus `CLAUDE_CODE_OAUTH_TOKEN` | The workflows authenticate as the Apps and call Claude. |
| 6 | Open the install PR | Adds the workflow files and starter config if missing or drifted. Merging it triggers `install.yml`. |
| 7 | Or dispatch `install.yml` | Only when nothing needs adding (a re-run): the installer runs the workflow for you. |
| 8 | `install.yml`: sync labels | The pipeline routes on labels ([`.github/labels.json`](../.github/labels.json)). |

The PR in step 6 writes under `.github/workflows/`, so a classic `gh` token needs the
`workflow` scope. The installer checks for it up front. `--dry-run` previews every step.

## Default-branch protection

`github-actions[bot]` and `claude[bot]` must not be on the default branch's push allowlist.
Keep the three interns Apps off it too; the installer doesn't check them yet
([#366](https://github.com/abi83/interns/issues/366)).

| Default branch | Result |
|---|---|
| requires a PR review, no bot on the allowlist | passes |
| protected, but no PR review required | **fails**: require pull request reviews, re-run |
| unprotected | installer applies the baseline: PR + 1 approval, no force-push, no deletion |
| protected, but your `gh` session lacks admin | **fails**: re-auth with admin, re-run |
| `github-actions[bot]` or `claude[bot]` is on the allowlist | **fails**: remove it, re-run |

If an org-wide ruleset (or similar) enforces protection where the check can't see it, pass
`--branch-protection-handled-externally`; it applies only when the branch is unprotected.

## GitHub Apps

Three Apps, `interns-{coder,reviewer,triage}-<owner>`, each minted with one "Create GitHub App"
click (App Manifest flow). You then install each on the repo; the installer prints the links.

Why three: [Trust model](architecture.md#trust-model).

Permissions are fixed in [`apps.py`](../installer/src/interns_install/apps.py): coder and
reviewer get Contents, Pull requests and Issues (read and write), Checks and Metadata (read);
triage gets only Issues (read and write) and Metadata (read). No webhooks.

**One App, many repos.** Apps belong to an account; only the installation and the secrets are
per repo. For a second repo under the same account, reuse the Apps: pass
`--{coder,reviewer,triage}-client-id`, or answer the installer's prompt. For the key, paste
the PEM the first repo stores or generate another (extra keys don't revoke the others). Then
install the App on the new repo.

## Secrets and variables

The installer writes them. It prompts you to paste `CLAUDE_CODE_OAUTH_TOKEN` (run
`claude setup-token` locally; Claude Pro or Max), and an existing secret is left alone.

| Kind | Name |
|---|---|
| Secret | `CLAUDE_CODE_OAUTH_TOKEN` |
| Secret | `INTERNS_{CODER,REVIEWER,TRIAGE}_APP_PRIVATE_KEY` |
| Variable | `INTERNS_{CODER,REVIEWER,TRIAGE}_CLIENT_ID` |

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

Missing files are added. The three workflow files and the dashboard page are re-synced if they
drifted; `interns.yml` and the Makefile are never overwritten.
Merge the PR: the push to `install.yml` triggers it and the labels sync.
`--issue-templates` also adds the default [issue templates](../templates/issue) when the repo
has none.

### Versions

The stubs pin `@v0`, a floating tag moved on every release, like `actions/checkout@v4`, so fixes
reach you with no edits. Before 1.0, breaking changes also ship as minor releases and move `v0`.
For a reproducible pin use a specific release tag. `next` tracks `main` (internal testing; set
`INTERNS_REF=next` when installing). Releases are cut by
[release-please](https://github.com/googleapis/release-please) from conventional commits.

## Doing it by hand

Without `interns-install`: create the three Apps with the permissions above and install them,
add the secrets and variables, set branch protection, enable Pages, create the
`interns-metrics` branch ([metrics](metrics.md)), and commit the files from
[`templates/workflows/`](../templates/workflows) yourself. Then run
`gh workflow run install.yml` to sync labels. `.github/interns.yml` is optional; use only the keys you override, with
`defaults.yml` as the reference.
