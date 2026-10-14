# Configuration

Defaults live in one file, [`templates/config/defaults.yml`](../templates/config/defaults.yml)
(keys, values and comments; validated by [`interns.schema.json`](../.github/interns.schema.json)).
The installer renders your `.github/interns.yml` from it with every key commented out. Uncomment a
key only to override it; the rest follows interns' defaults as they change. Precedence per key:
`agents.<name>` > `defaults` > built-in. Example, auto-proceed `L` issues to the coder:

```yaml
auto_proceed:
  L: true
```

## Reviewer CI gate

The reviewer runs only when all of a PR's checks are green. A red or cancelled check routes the PR
to a human. It starts on `workflow_run: completed` of any other workflow in the repo (not the
pipeline's own), so no runner polls CI. Checks still running after the short
`checks.timeout_seconds` wait skip that run; the next workflow to complete triggers it again
([`domain/checks.py`](../interns/src/interns/domain/checks.py)).

Name non-blocking advisory checks (preview deploys, coverage deltas) under `checks.ignore` to keep
them out of the gate.

`agents.reviewer.trigger` narrows which PRs get reviewed: `coder_prs`, `human_prs`, and
`rereview_on_push` (`false` reviews a PR only when it is opened or marked ready). Draft PRs, fork
PRs and PRs from bots other than the coder App are never reviewed; a manual `workflow_dispatch`
always runs ([`domain/routing.py`](../interns/src/interns/domain/routing.py)).

## Agent tools

Each agent has a fixed tool set. Extend it with `allowed_tools`, narrow it with `disallowed_tools`,
per agent or under `defaults`. Lists from both scopes add up, and a deny always wins (examples in
the config file).

**A wildcard like `Bash(npm run *)` is arbitrary code execution via package scripts.** Keep patterns
narrow and under the one agent that needs them. See the
[trust model](architecture.md#trust-model).

## Wiki

`wiki.enabled: true` (with `wiki.url`, e.g. `owner/repo.wiki`) checks the wiki out next to the repo
checkout, as `../<repo>.wiki`, for every agent to read.

## Makefile contract

The coder runs on a fresh runner, so the repo's [`Makefile`](../templates/config/Makefile) is the
language-agnostic contract:

- `setup` installs dependencies. `make setup` runs before the coder, in both the initial and fix
  rounds; a non-zero exit fails the job before any Claude tokens are spent.
- `test` and `build` are run by the coder before it pushes. The reviewer does not run them; it
  relies on CI.

Each target ships as a stub containing `INTERNS: not configured`. A stubbed or absent `setup` is
skipped with a warning; a run that leaves `test`/`build` stubbed nags the issue. The installer
appends the `setup` stub to an existing `Makefile` that lacks the target.
