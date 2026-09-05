## Install the interns pipeline

Opened by the **Install interns** workflow.

- **Labels** — the versioned manifest is already synced to this repo (that step
  runs unconditionally, not in this PR).
- **Caller stubs** — `.github/workflows/{issue,code}-pipeline.yml` delegate to
  the reusable cores in `abi83/interns`, pinned to a release tag.
- **Config** — `.github/interns.yml` holds per-agent limits; every key is
  optional and falls back to the interns defaults.

Existing files were left untouched — re-running the installer only adds what is
missing and re-syncs label drift.

### Before merging

`interns-install` already wrote the App secrets/variables and verified
branch protection and Pages locally before opening this PR. The one thing
still manual: install each GitHub App (`interns-reviewer`, `interns-coder`)
on this repo, using the links it printed.

See the interns README for the full prerequisite list.
