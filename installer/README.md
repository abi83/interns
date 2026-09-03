# interns-install

Interactive local front end for provisioning a repo for the interns pipeline.

`install.yml` does everything a headless GitHub Actions run can — label sync,
caller-stub PR, starter config, safety checks. It deliberately can't do the two
things that keep setup heavy:

- **create the bot GitHub Apps** — needs an interactive browser click
- **write repo secrets / variables** — `secrets: write` isn't grantable to
  `GITHUB_TOKEN`

`interns-install` fills exactly that gap, then hands off to `install.yml`.

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
(`gh auth login`) with a token that can write repo secrets — classic scope
`repo`, or a fine-grained PAT with **Secrets: write** and **Variables: write**
on the target repo. Python 3.12+ (managed by `uv`).

## What it does

1. Mints `interns-reviewer` and `interns-coder` via the GitHub App Manifest
   flow — a localhost callback server, one "Create GitHub App" click per app.
2. Writes `REVIEWER_APP_ID` / `CODER_APP_ID` (variables) and
   `REVIEWER_APP_PRIVATE_KEY` / `CODER_APP_PRIVATE_KEY` / `CLAUDE_CODE_OAUTH_TOKEN`
   (secrets). Private keys go straight from the manifest conversion response
   into the secret, never to disk.
3. Dispatches `install.yml` (or prints the manual step if the target repo has
   no wrapper yet).
4. Prints a summary and a checklist of anything still manual — installing each
   App on the repo, branch protection the token couldn't set.

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
