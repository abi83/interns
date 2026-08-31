# interns

A tireless team of interns that refine issues, estimate them, open PRs, and
review each other's work — with a human in the loop on every merge.

The pipeline drives [Claude Code](https://github.com/anthropics/claude-code)
over a checked-out repo, respects its `CLAUDE.md` / `AGENTS.md`, and runs
entirely in the consumer repo's GitHub Actions — no hosted service.

Status: early. Consumed by [`abi83/prepify`](https://github.com/abi83/prepify).
Design and roadmap: [abi83/prepify#130](https://github.com/abi83/prepify/issues/130).

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
`REVIEWER_APP_PRIVATE_KEY` secrets, a `REVIEWER_APP_ID` var, the
`status:*` / `type:*` / `size:*` labels, and default-branch protection.
Optional: `.github/agent-pipeline.yml` (per-agent model + limits).

A one-shot installer that provisions all of that is tracked in
[abi83/prepify#153](https://github.com/abi83/prepify/issues/153) /
[#154](https://github.com/abi83/prepify/issues/154). A fuller README —
pipeline flow, label state table — is [abi83/prepify#163](https://github.com/abi83/prepify/issues/163).

## Layout

| | |
|---|---|
| `.github/workflows/*-pipeline.yml` | reusable `workflow_call` cores |
| `.github/actions/*` | composite actions the cores use |
| `.github/scripts/pipeline/*` | pipeline steps (+ `bats` tests) |
| `.github/scripts/gh-safe/*` | the narrow `gh` surface the agents may call |
| `.github/prompts/*` | agent prompts, layered over the consumer's `CLAUDE.md` |
| `templates/issue/*` | default issue templates |

## License

MIT
