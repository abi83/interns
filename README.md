# interns

A tireless team of interns that refine issues, estimate them, open PRs, and
review each other's work — with a human in the loop on every merge.

The pipeline drives [Claude Code](https://github.com/anthropics/claude-code)
over a checked-out repo, respects its `CLAUDE.md` / `AGENTS.md`, and runs
entirely in the consumer repo's GitHub Actions — no hosted service.

Status: early. Consumed by [`abi83/prepify`](https://github.com/abi83/prepify).
Design and roadmap: [#3](https://github.com/abi83/interns/issues/3).

## Consuming it

Commit two thin caller workflows that own the triggers and delegate to the
reusable cores, pinned to an exact tag:

```yaml
# .github/workflows/issue-pipeline.yml
jobs:
  pipeline:
    uses: abi83/interns/.github/workflows/issue-pipeline.yml@v0.1.0
    secrets: inherit
    with: { phase: ${{ inputs.phase }} }
```

```yaml
# .github/workflows/code-pipeline.yml
jobs:
  pipeline:
    uses: abi83/interns/.github/workflows/code-pipeline.yml@v0.1.0
    secrets: inherit
    with: { phase: ${{ inputs.phase }} }
```

Needs, in the consumer repo: `CLAUDE_CODE_OAUTH_TOKEN` +
`REVIEWER_APP_PRIVATE_KEY` + `CODER_APP_PRIVATE_KEY` secrets, `REVIEWER_APP_ID`
and `CODER_APP_ID` vars (the reviewer and coder run as separate GitHub Apps),
the `status:*` / `type:*` / `size:*` / `priority:*` / `pr:*` labels, and
default-branch protection.
Optional: `.github/agent-pipeline.yml` (per-agent model + limits).

### Installer

`.github/workflows/install.yml` provisions a consumer repo. It syncs the
versioned label manifest ([`.github/labels.json`](.github/labels.json) —
every `status:*` / `type:*` / `size:*` / `priority:*` / `pr:*` the state
machine relies on) and opens a PR with the thin caller stubs plus a starter
`.github/agent-pipeline.yml`. It's idempotent: re-running fixes label drift
and only adds stub files that are missing, never overwriting a hand-edited
one. Label sync is additive — labels absent from the manifest are left
alone.

Before opening the PR it runs safety checks and refuses to finish if one
fails: the default branch must be protected so the agent identities can't
push to it (it applies a baseline — require a PR, one approval, no force
pushes — when protection is absent, unless
`allow_agent_push_to_default_branch: true` in the config opts out); the
`CLAUDE_CODE_OAUTH_TOKEN`, `REVIEWER_APP_PRIVATE_KEY` and
`CODER_APP_PRIVATE_KEY` secrets and the `REVIEWER_APP_ID` / `CODER_APP_ID`
variables must exist; and Pages is enabled (switched on with the GitHub Actions
build type when off). Managing branch protection and Pages needs a token with
`administration` scope; reading secrets and variables needs more than
`GITHUB_TOKEN` carries, so those checks downgrade to a warning when they can't
list them.

A fuller README — pipeline flow, label state table — is
[#10](https://github.com/abi83/interns/issues/10).

## Pipeline metrics

Every agent run appends one machine-readable record per `(run, job)` to
`metrics.jsonl` on an orphan `metrics` branch in the consumer repo — tokens
(per model, sub-agents included), tool-call counts, `num_turns`, durations,
cost, and the agent's process result. A final `metrics` job on each workflow
run gathers the records its agent jobs uploaded and commits them in a single
push (serialised by a `metrics-append` concurrency group, fetch-rebased on a
race).

The branch is created automatically on the first run — no manual seeding. The
record shape is versioned by `schema_version` and specified in
[`.github/pipeline-metrics.schema.json`](.github/pipeline-metrics.schema.json);
bump it and the `SCHEMA_VERSION` constant in `extract-metrics.sh` together on
any breaking change. Read the log from any client with a single unauthenticated
fetch of `raw.githubusercontent.com/<owner>/<repo>/metrics/metrics.jsonl`.

## Layout

| | |
|---|---|
| `.github/workflows/*-pipeline.yml` | reusable `workflow_call` cores |
| `.github/actions/*` | composite actions the cores use |
| `.github/scripts/pipeline/*` | pipeline steps (+ `bats` tests) |
| `.github/scripts/gh-safe/*` | the narrow `gh` surface the agents may call |
| `.github/scripts/install/*` | installer steps (label sync, safety checks, + `bats` tests) |
| `.github/labels.json` | versioned label manifest (+ `.schema.json`) |
| `.github/prompts/*` | agent prompts, layered over the consumer's `CLAUDE.md` |
| `templates/issue/*` | default issue templates |
| `templates/workflows/*`, `templates/config/*` | caller stubs + starter config the installer commits |

## License

MIT
