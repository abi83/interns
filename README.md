# interns

A tireless team of interns that refine issues, estimate them, open PRs, and
review each other's work — while a human stays in the loop on every merge.

The pipeline drives [Claude Code](https://github.com/anthropics/claude-code) over
a checked-out repo and respects its `CLAUDE.md` / `AGENTS.md`. It runs entirely
in the consumer repo's GitHub Actions — no hosted service, no webhook receiver.

Tracking issue: [abi83/prepify#130](https://github.com/abi83/prepify/issues/130).

## What's here

| Path | |
|---|---|
| `.github/workflows/issue-pipeline.yml` | reusable `workflow_call` core — refine + estimate |
| `.github/workflows/code-pipeline.yml` | reusable `workflow_call` core — coder + reviewer |
| `.github/actions/*` | composite actions the cores use |
| `.github/scripts/pipeline/*` | pipeline shell steps (+ `bats` tests) |
| `.github/scripts/gh-safe/*` | the narrow `gh` surface the agents are allowed to call |
| `.github/prompts/*` | the agent prompts, layered over the consumer's `CLAUDE.md` |
| `.github/agent-pipeline.schema.json` | schema for the consumer's `.github/agent-pipeline.yml` |

Each reusable job self-checks-out this repo at its own tag into `.interns/` and
runs the assets from there, so a consumer never vendors any of it.

## Consuming it

Commit two thin caller workflows to your repo. They own the triggers and
delegate everything else:

```yaml
# .github/workflows/issue-pipeline.yml
name: Issue Refinement & Estimation
on:
  issues:
    types: [labeled]
  workflow_dispatch:
    inputs:
      issue_number: { description: Issue number, required: true }
      phase: { description: refine | estimate, required: true, type: choice, options: [refine, estimate] }
permissions:
  issues: write
  id-token: write
jobs:
  pipeline:
    uses: abi83/interns/.github/workflows/issue-pipeline.yml@v0.1.0
    secrets: inherit
    with:
      issue_number: ${{ inputs.issue_number }}
      phase: ${{ inputs.phase }}
```

```yaml
# .github/workflows/code-pipeline.yml
name: Coding Agents
on:
  issues:
    types: [labeled]
  pull_request:
    types: [opened, synchronize, reopened]
  workflow_dispatch:
    inputs:
      phase: { description: coder | reviewer, required: true, type: choice, options: [coder, reviewer] }
permissions:
  contents: write
  pull-requests: write
  issues: write
  actions: write
  id-token: write
jobs:
  pipeline:
    uses: abi83/interns/.github/workflows/code-pipeline.yml@v0.1.0
    secrets: inherit
    with:
      phase: ${{ inputs.phase }}
```

Pin an **exact** tag, not a moving `@v0` — the job self-checks-out its assets at
the same ref, and a moving major tag would let the two drift.

### Required in the consumer repo

- Secrets: `CLAUDE_CODE_OAUTH_TOKEN`; `REVIEWER_APP_PRIVATE_KEY` for the reviewer
- Variable: `REVIEWER_APP_ID` (the reviewer runs as its own GitHub App so it can
  approve the coder's PRs)
- The `status:*` / `type:*` / `size:*` label set the state machine moves between
- Default-branch protection — the agents commit through PRs only

### Optional

- `.github/agent-pipeline.yml` — per-agent model and execution limits
  (precedence: this file > `PIPELINE_*` Actions vars > built-in defaults)
- Variable `WIKI_REPO` — a wiki repo to check out alongside the code

An installer that provisions the labels, caller stubs, and safety checks is
tracked separately ([#153](https://github.com/abi83/prepify/issues/153),
[#154](https://github.com/abi83/prepify/issues/154)).

## License

MIT
