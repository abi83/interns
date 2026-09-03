# CLAUDE.md

Guidance for agents working in this repo.

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
