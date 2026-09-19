# CLAUDE.md

Guidance for agents working in this repo.

## Stack

Python, stdlib only. Bash scripts are being migrated to Python (abi83/interns#155).

## What this is

`interns` drives Claude Code over consumer repos' GitHub issues (refine →
estimate → code → review), running as GitHub Actions workflows. See
[README.md](README.md) for the full pipeline.

## Coding Guidelines

- **Fail fast.** Invalid state throws — no `catch` that swallows and returns
  a default/empty result.
- **No nested if-else.** Guard clauses / early returns. Still nested after
  that — extract a function.
- **Minimize optional fields.** Don't add one just because one code path
  happens not to set it.

## Comments

Prefer self-documenting code — clear names, small functions, obvious control
flow. Add a comment only when it carries information the code cannot: a
non-obvious *why*, a workaround and the reason for it, a subtle invariant or
gotcha. Don't restate what the next line does, and don't write narrated
section headers. When in doubt, cut it.

## Portability

This pipeline runs in any consumer repo. Keep code, comments, and docs free of
references to specific consumer repos or their issue numbers — refer to "the
consumer repo" generically. Cross-repo links belong in the README only.

## Issue tracking

This repo's own work is tracked as GitHub issues. Run `gh issue view <n>`
before starting one; PR against `main`. A TODO/FIXME needs a linked issue,
not just a description.
