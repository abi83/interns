## Install the interns pipeline

Opened by the **Install interns** workflow.

- **Labels** — the versioned manifest is already synced to this repo (that step
  runs unconditionally, not in this PR).
- **Caller stubs** — `.github/workflows/{issue,code}-pipeline.yml` delegate to
  the reusable cores in `abi83/interns`, pinned to a release tag.
- **Config** — `.github/agent-pipeline.yml` holds per-agent limits; every key is
  optional and falls back to the interns defaults.

Existing files were left untouched — re-running the installer only adds what is
missing and re-syncs label drift.

### Before merging

- Add the `CLAUDE_CODE_OAUTH_TOKEN`, `REVIEWER_APP_PRIVATE_KEY` and
  `CODER_APP_PRIVATE_KEY` secrets and the `REVIEWER_APP_ID` and `CODER_APP_ID`
  variables (two GitHub Apps — one reviewer, one coder).
- Turn on default-branch protection.

See the interns README for the full prerequisite list.
