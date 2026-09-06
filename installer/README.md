# interns-install

The local CLI half of repo provisioning: creates the two GitHub Apps, writes
repo secrets and variables, checks default-branch protection and Pages, then
hands off to `install.yml`. It runs locally because `GITHUB_TOKEN` is never
granted admin access or `secrets: write`.

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
