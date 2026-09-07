# interns-install

The local CLI half of repo provisioning: creates the two GitHub Apps, writes
repo secrets and variables, checks default-branch protection and Pages, then
hands off to `install.yml`. It runs locally because `GITHUB_TOKEN` is never
granted admin access or `secrets: write`.

`install.yml` is a reusable workflow in `abi83/interns`, so the handoff needs a
local caller. If the repo has none, the CLI opens a one-file PR adding
`.github/workflows/install.yml` (the wrapper from `templates/workflows/`);
merge it and re-run the CLI, which then dispatches it.

Because that PR writes under `.github/workflows/`, a classic `gh` token needs
the `workflow` scope; the CLI checks for it up front (unless `--skip-handoff`)
and stops with a fix hint rather than 404ing at the handoff.

What it does, step by step, and how it fits the rest of setup:
[the root README](../README.md).

Python, stdlib only. Package root is this directory; it's published straight
from here via `uvx --from git+…#subdirectory=installer`.

## Run

Via the bootstrap in the root README, or directly with `uv`:

```sh
uvx --from git+https://github.com/abi83/interns.git@v0.1.0#subdirectory=installer interns-install
```

`interns-install --help` lists every flag.

## Develop

```sh
cd installer
PYTHONPATH=src python -m unittest discover -s tests -v
```
