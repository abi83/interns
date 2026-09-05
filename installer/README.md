# interns-install

Interactive local front end for provisioning a repo for the interns pipeline.

`install.yml` does everything a headless GitHub Actions run can — label sync,
caller-stub PR, starter config. It deliberately can't do the things that keep
setup heavy, because `GITHUB_TOKEN` is never grantable admin access or
`secrets: write`:

- **create the bot GitHub Apps** — needs an interactive browser click
- **write repo secrets / variables**
- **read or write default-branch protection, and enable Pages** — GitHub's
  branch-protection and Pages APIs both require admin access to the repo

`interns-install` fills exactly that gap, running locally with your own
already-admin `gh` session, then hands off to `install.yml`.

## Run it

```sh
curl -LsSf https://raw.githubusercontent.com/abi83/interns/v0.1.0/install.sh | sh
```

The bootstrap installs [`uv`](https://docs.astral.sh/uv/) if missing and runs
the CLI. With `uv` already present:

```sh
uvx --from git+https://github.com/abi83/interns.git@v0.1.0#subdirectory=installer interns-install
```

Prerequisites: the [GitHub CLI](https://cli.github.com/) authenticated
(`gh auth login`) as an account with **admin access to the target repo** —
needed to write repo secrets, and to read/fix branch protection and Pages.
Python 3.12+ (managed by `uv`).

## What it does

1. Checks the default branch is protected against the bot identities
   (`github-actions[bot]`, `claude[bot]`, the two Apps) — applies a baseline
   (PR + 1 approval required, no force-push/deletion) if it's unprotected,
   fails if a bot is on the push allowlist or your session can't verify it.
2. Checks GitHub Pages is enabled (the dashboard's deployment target) — turns it
   on if it's off.
3. Mints `interns-reviewer` and `interns-coder` via the GitHub App Manifest
   flow — a localhost callback server, one "Create GitHub App" click per app.
4. Writes `INTERNS_REVIEWER_APP_ID` / `INTERNS_CODER_APP_ID` (variables) and
   `INTERNS_REVIEWER_APP_PRIVATE_KEY` / `INTERNS_CODER_APP_PRIVATE_KEY` /
   `CLAUDE_CODE_OAUTH_TOKEN` (secrets). Private keys go straight from the
   manifest conversion response into the secret, never to disk.
5. Dispatches `install.yml` (or prints the manual step if the target repo has
   no wrapper yet).
6. Prints a summary and a checklist of anything still manual — installing each
   App on the repo.

## Flags

| flag | effect |
|---|---|
| `--repo OWNER/NAME` | target repo (default: what `gh` resolves for the cwd) |
| `--yes` | assume yes for every prompt |
| `--dry-run` | print every mutation without performing it |
| `--issue-templates[=true\|false]` | ask `install.yml` to add the default issue templates |
| `--handoff-ref REF` | ref to dispatch `install.yml` on (default: target default branch) |
| `--skip-handoff` | don't touch `install.yml` |

## Develop

```sh
cd installer
PYTHONPATH=src python -m unittest discover -s tests -v
```
