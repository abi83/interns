# CLAUDE.md

## Stack

Python. The `interns` and `installer` packages are stdlib only; third-party
dependencies live only in `gh_issues_mcp/`. The `yq` binary is a runtime prerequisite
(config parsing). `install.sh` is intentionally shell: it runs before Python/uv
exist.

## What this is

`interns` drives Claude Code over consumer repos' GitHub issues (refine →
estimate → code → review), running as GitHub Actions workflows. See
[README.md](README.md) for the pitch and
[docs/architecture.md](docs/architecture.md) for how it works.

## Coding Guidelines

- **Fail fast.** Invalid state throws — no `catch` that swallows and returns
  a default/empty result.
- **No nested if-else.** Guard clauses / early returns. Still nested after
  that — extract a function.
- **Minimize optional fields.** Don't add one just because one code path
  happens not to set it.
- **One error-swallowing mechanism.** Failures raise unless routed through
  `best_effort.call` with a non-empty reason string. No other code swallows.

## Comments

Prefer self-documenting code — clear names, small functions, obvious control
flow. Add a comment only when it carries information the code cannot: a
non-obvious *why*, a workaround and the reason for it, a subtle invariant or
gotcha. Don't restate what the next line does, and don't write narrated
section headers. When in doubt, cut it.

## Portability

This pipeline runs in any consumer repo. Keep code, comments, and docs free of
references to specific consumer repos or their issue numbers — refer to "the
consumer repo" generically.

## Tests

Read [docs/test-guide.md](docs/test-guide.md) before writing any test.

## Issue tracking

This repo's own work is tracked as GitHub issues. Run `gh issue view <n>`
before starting one; PR against `main`. A TODO/FIXME needs a linked issue,
not just a description.

## Merging

PRs are squash-merged. When planning several dependent PRs, don't stack
branches on each other: a stacked branch conflicts once its base is
squashed. Either wait for the base to merge and branch from `main`, or
rebase the dependent branch with `git rebase --onto origin/main <old-base-tip>`
after the base merges.

## Architecture

Read [docs/architecture.md](docs/architecture.md) before changing the pipeline:
intent, layers, invariants, the label state machine, and checklists for adding a
step, label, MCP tool or config key.
