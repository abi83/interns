"""Which caller-stub / config files a consumer repo is missing or has
drifted from the `abi83/interns` template, and the PR body describing it."""

from __future__ import annotations

import os

from . import gh_admin

WORKFLOW = "install.yml"
INTERNS_REPO = "abi83/interns"

# Ref to copy the install wrapper from. install.sh exports INTERNS_REF; the
# default matches the pin baked into the templates.
INTERNS_REF = os.environ.get("INTERNS_REF") or "v0"

# Templates leave the interns ref as this placeholder so the pin always tracks
# the installer version -- both in the `uses:` line and in each wrapper's
# `ref:` fallback (never the consumer's commit SHA, see #73).
REF_PLACEHOLDER = "__INTERNS_REF__"

# Caller stubs, source path in INTERNS_REPO -> destination path in the
# consumer (GITHUB_TOKEN can't push .github/workflows/*, see #74). Meant to
# stay identical to the template, so a drifted copy is re-synced, not just
# added when absent (#88).
WRAPPER_FILES = {
    f"templates/workflows/{WORKFLOW}": f".github/workflows/{WORKFLOW}",
    "templates/workflows/issue-pipeline.yml": ".github/workflows/issue-pipeline.yml",
    "templates/workflows/code-pipeline.yml": ".github/workflows/code-pipeline.yml",
}

# Seeded once, then expected to carry consumer-local edits -- added when
# missing, never overwritten.
CONFIG_FILES = {
    "templates/config/interns.yml": ".github/interns.yml",
    "templates/config/Makefile": "Makefile",
}

INSTALL_FILES = {**WRAPPER_FILES, **CONFIG_FILES}

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
- **`Makefile`** — `test`/`build` targets the coder and reviewer run before a PR
  is opened or updated. Fill them in with this repo's real commands; left
  empty, the pipeline treats testing as not yet configured rather than
  failing every PR.

Missing files are added; a wrapper file (`install.yml`, `issue-pipeline.yml`,
`code-pipeline.yml`) that's already present but out of date with the current
template is re-synced too. `.github/interns.yml` and `Makefile` are only
added when absent — an existing one is left untouched, since it's expected to
carry consumer-local edits.

After merging,
re-run `interns-install` (or dispatch **Install interns** from the Actions tab)
to sync the label manifest.
"""


def collect_missing_files(repo: gh_admin.Repo, base: str,
                          issue_templates: bool) -> dict[str, tuple[str, str | None]]:
    """Destination path -> (new content, current sha or None) for every file
    that needs adding or re-syncing. The sha, when present, tells `put_file`
    to update rather than create."""
    wanted: dict[str, tuple[str, str | None]] = {}

    for src, dest in WRAPPER_FILES.items():
        content = gh_admin.get_file(INTERNS_REPO, src, INTERNS_REF).replace(REF_PLACEHOLDER, INTERNS_REF)
        existing = gh_admin.get_existing_file(repo.slug, dest, base)
        if existing is None:
            wanted[dest] = (content, None)
        elif existing[0] != content:
            wanted[dest] = (content, existing[1])

    for src, dest in CONFIG_FILES.items():
        if not gh_admin.path_exists(repo.slug, dest, base):
            content = gh_admin.get_file(INTERNS_REPO, src, INTERNS_REF).replace(REF_PLACEHOLDER, INTERNS_REF)
            wanted[dest] = (content, None)

    if issue_templates and not gh_admin.path_exists(repo.slug, ".github/ISSUE_TEMPLATE", base):
        for name in gh_admin.list_dir(INTERNS_REPO, "templates/issue", INTERNS_REF):
            content = gh_admin.get_file(INTERNS_REPO, f"templates/issue/{name}", INTERNS_REF)
            wanted[f".github/ISSUE_TEMPLATE/{name}"] = (content, None)
    return wanted
