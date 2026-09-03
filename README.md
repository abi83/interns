# interns

A tireless team of interns that refine issues, estimate them, open PRs, and
review each other's work — with a human in the loop on every merge.

The pipeline drives [Claude Code](https://github.com/anthropics/claude-code)
over a checked-out repo, respects its `CLAUDE.md` / `AGENTS.md`, and runs
entirely in the consumer repo's GitHub Actions — no hosted service.

Status: early. Consumed by [`abi83/prepify`](https://github.com/abi83/prepify).
Design and roadmap: [#3](https://github.com/abi83/interns/issues/3).

## What it does

Four agents pick issues up by label and hand them along a fixed track:

| Agent | Trigger | Does | Leaves |
|---|---|---|---|
| **Refiner** | `status:needs-refinement` on an issue | picks the type, checks the draft against the codebase and wiki, rewrites the body into the type's template, posts a blockers/dependencies comment | `status:refined` |
| **Estimator** | `status:refined` | reads the code the Scope touches, scores blast radius / touch / human involvement / review overhead, rolls that into a size | `status:estimated` + `size:*` |
| **Coder** | `status:ready` (owner-approved) on a `type:coding-task` or `type:bug` | implements every Acceptance Criteria item, writes tests, opens a PR that `Closes #N` | `status:in-progress`, a PR labelled `pr:in-review` |
| **Reviewer** | a PR opened/updated by the coder (or a human) | waits for the `test` / `build` checks, reviews the diff against the linked issue, submits `APPROVE` or `REQUEST_CHANGES` | PR approved, or a coder fix round, or `pr:needs-attention` |

The human owner does two things: approve the estimate (move `status:estimated`
→ `status:ready`), and merge the final PR. Everything between is automated, and
anything the automation can't finish is parked on `status:needs-attention` /
`pr:needs-attention` rather than guessed at.

```mermaid
flowchart TD
    new([issue opened]) --> nr["ISSUE: status:needs-refinement"]
    nr -->|refiner| refined["ISSUE: status:refined"]
    nr -.->|needs a decision| na["ISSUE: status:needs-attention"]
    refined -->|estimator| est["ISSUE: status:estimated + size:*"]
    refined -.->|epic| ready
    refined -.->|needs a decision| na
    est -->|owner approves| ready["ISSUE: status:ready"]
    ready -->|coder| inprog["ISSUE: status:in-progress"]
    inprog -.->|no PR opened / coder declined| na

    inprog -->|coder opens PR| loop

    subgraph loop [coder–reviewer loop]
        inreview["PR: pr:in-review"] -->|reviewer: REQUEST_CHANGES| coding["PR: pr:coding"]
        coding -->|coder pushes a fix| inreview
    end

    loop -->|reviewer: APPROVE| approved["PR approved"]
    approved -->|owner merges| closed(["ISSUE: closed"])
    loop -.->|red checks / 2nd review still requests changes / 5-review ceiling| prna["PR: pr:needs-attention"]
    loop -.->|coder declines the fix round| na
```

## Label state machine

The installer syncs these from the versioned manifest
([`.github/labels.json`](.github/labels.json)). Label sync is additive — labels
not in the manifest are left alone.

### `status:*` — issue lifecycle (mutually exclusive)

| Label | Meaning                                                | Set by                                                                      | Moves to                                                                                                                                                                       |
|---|--------------------------------------------------------|-----------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `status:needs-refinement` | awaiting the refiner                                   | **human**, triggers the refinement-estimation pipeline                      | `status:refined`, or `status:needs-attention` if the refiner needs a decision                                                                                                  |
| `status:refined` | refined, awaiting estimation                           | refiner                                                                     | `status:estimated` (+ `size:*`); `status:ready` directly for a `type:epic`; `status:needs-attention` if unsizeable                                                             |
| `status:estimated` | estimated — waiting on the owner to approve or comment | estimator                                                                   | `status:ready` set by human to thrigger the coder, or an human **comment** for triggering conversational follow-up TBD in ([#11](https://github.com/abi83/interns/issues/11)). |
| `status:ready` | approved for the coder                                 | **human**, triggers the coder-reviewer pipeline | `status:in-progress` when the coder starts; `status:needs-attention` if the issue isn't a `type:coding-task` / `type:bug`                                                      |
| `status:in-progress` | a coder-reviewer loop is in progress                   | coder                                                                       | issue closed on merge, or `status:needs-attention`                                                                                                                             |
| `status:needs-attention` | pipeline stalled — a human needs to look               | any agent                                                                   | cleared when a human re-dispatches (the coder drops it on pickup)                                                                                                              |

### `pr:*` — PR pipeline (mutually exclusive)

Once the coder opens a PR the work enters the **coder–reviewer loop**: the
reviewer holds `pr:in-review`, and on `REQUEST_CHANGES` it hands back to the
coder as `pr:coding`; the coder pushes a fix and hands back as `pr:in-review`.
Two limits bound the loop:

- **One automatic fix round.** The coder gets a single fix attempt. If the
  reviewer's *second* review still requests changes, the PR goes to
  `pr:needs-attention` — the automatic loop didn't converge.
- **Five reviewer runs per PR, hard.** A backstop for after escalation: a human
  can keep pushing commits and each one still spawns a reviewer run. At 5 total
  reviews on the PR, automatic review stops entirely and stays manual.

Red `test` / `build` checks also send the PR straight to `pr:needs-attention`,
with no fix round.

| Label | Meaning | Set by | Moves to |
|---|---|---|---|
| `pr:coding` | a coder agent is on this PR (a fix round) | reviewer, when it requests changes | `pr:in-review` after the coder pushes |
| `pr:in-review` | a reviewer agent is on this PR | coder, at hand-off | cleared on `APPROVE`; `pr:coding` on `REQUEST_CHANGES`; `pr:needs-attention` on escalation |
| `pr:needs-attention` | PR pipeline stalled — a human needs to look | reviewer gate | cleared by the next agent pickup or an `APPROVE` |

An approved PR carries **no** `pr:*` label — the native review state is the
signal. List the PRs waiting on a human with
`gh pr list --label pr:needs-attention`.

### `type:*` — set by the refiner (or a human at creation), never changed after

| Label | Estimated? | Coder implements? |
|---|---|---|
| `type:coding-task` | yes | yes |
| `type:bug` | yes | yes |
| `type:spike` | yes | no — a human does the investigation |
| `type:epic` | no — skipped straight to `status:ready` | no — a human breaks it into sub-issues |

There is no agent for spikes or epics — the pipeline only refines them (and
estimates the spike). Once refined, the work is a human's: a spike that reaches
`status:ready` (or an epic, via its estimate-phase bypass) is bounced straight
to `status:needs-attention` by the coder's type gate.

### `size:*` and `priority:*`

`size:XS` … `size:XL` are added by the estimator alongside `status:estimated`;
`size:XL` also gets a `SPLIT:` note on the estimate comment. `priority:low` …
`priority:urgent` are owner triage labels — the pipeline reads neither; they
exist for humans sorting the backlog.

## Setup

### 1. Register the two GitHub Apps

The pipeline runs the coder and the reviewer as **separate** GitHub App
identities so the reviewer can actually `APPROVE` a PR the coder authored
(GitHub forbids approving your own PR) and so branch protection can treat each
independently.

`interns-install` (below) mints both via the App Manifest flow. To create them
by hand instead, make two apps — `interns-coder` and `interns-reviewer` — with
the same permission set:

| Permission | Access | Why |
|---|---|---|
| Contents | Read and write | push branches |
| Pull requests | Read and write | open PRs, submit reviews, comment |
| Issues | Read and write | edit labels, comment |
| Checks | Read | reviewer reads check results |
| Metadata | Read | mandatory baseline |

No webhook, no subscribed events. **Install both apps on the consumer repo**
after creating them.

### 2. Secrets and variables

On the consumer repo (Settings → Secrets and variables → Actions):

| Kind | Name | Value |
|---|---|---|
| Secret | `CLAUDE_CODE_OAUTH_TOKEN` | OAuth token for `anthropics/claude-code-action` |
| Secret | `CODER_APP_PRIVATE_KEY` | `interns-coder` private key (PEM) |
| Secret | `REVIEWER_APP_PRIVATE_KEY` | `interns-reviewer` private key (PEM) |
| Variable | `CODER_APP_ID` | `interns-coder` App ID |
| Variable | `REVIEWER_APP_ID` | `interns-reviewer` App ID |

Optional variables (per-repo overrides of the pipeline defaults; the
[`.github/agent-pipeline.yml`](templates/config/agent-pipeline.yml) config file
wins over these):

| Variable | Default | Effect |
|---|---|---|
| `PIPELINE_MODEL` | per-agent built-in | model for every agent |
| `PIPELINE_MAX_TURNS` | 40 | agent turn ceiling |
| `PIPELINE_TIMEOUT_MINUTES` | 20 | per-run timeout |
| `PIPELINE_MAX_OUTPUT_TOKENS` | action default | output-token safety ceiling |
| `PIPELINE_COST_WARN_USD` | 2.0 | run-summary cost warning threshold |
| `WIKI_REPO` | unset | `owner/name` of a wiki repo to check out for the agents |

The consumer repo also needs `test` and `build` status checks on its PRs (from
its own `deploy.yml` or equivalent) — the reviewer waits on them and won't run
until both are green.

### 3. Default-branch protection

The agents run with the consumer repo's own credentials, so the default branch
must be protected against every bot identity — `github-actions[bot]`,
`claude[bot]`, and both apps. The installer's safety check requires, and
creates when absent (baseline: require a PR, one approval, no force pushes, no
deletions):

- a required pull-request review;
- **no** bot identity on the push allowlist.

Opt out with `allow_agent_push_to_default_branch: true` in
`.github/agent-pipeline.yml` only if protection already blocks the bots some
other way.

### 4. Run the installer

The supported 0.1.0 path is `interns-install` — a local, interactive CLI that
does the two things a headless Actions run can't: mint the apps (an interactive
browser click) and write the repo secrets/variables (`secrets: write` isn't
grantable to `GITHUB_TOKEN`). It then hands off to `install.yml`.

```bash
curl -LsSf https://raw.githubusercontent.com/abi83/interns/v0.1.0/install.sh | sh
```

The bootstrap installs [`uv`](https://docs.astral.sh/uv/) if missing; with `uv`
already present:

```bash
uvx --from git+https://github.com/abi83/interns.git@v0.1.0#subdirectory=installer interns-install
```

Needs the [GitHub CLI](https://cli.github.com/) authenticated (`gh auth login`)
with a token that can write repo secrets — classic scope `repo`, or a
fine-grained PAT with **Secrets: write** and **Variables: write** on the target
repo. Flags and details: [`installer/README.md`](installer/README.md).

`.github/workflows/install.yml` does the rest, and is idempotent:

- syncs the label manifest (re-running fixes label drift);
- runs the safety checks (§3, plus verifies the secrets/vars exist and enables
  GitHub Pages) and **refuses to finish if one fails**;
- opens a PR with the thin caller stubs and a starter `.github/agent-pipeline.yml`,
  adding only files that are missing — it never overwrites a hand-edited one.

Managing branch protection and reading secrets needs more than `GITHUB_TOKEN`
carries. Pass a repo-admin token as the `admin_token` secret when calling
`install.yml`, or set branch protection by hand; without it those checks
downgrade to a warning but a *definitively* unprotected branch or missing
secret is still a hard failure.

The fully manual path — create the apps, add the secrets, sync labels, commit
the stubs yourself — stays supported as the fallback.

### 5. Commit the caller stubs

The installer PR adds two thin callers that own the triggers and delegate to
the reusable cores, pinned to an exact tag. Merge that PR, or commit them
yourself:

```yaml
# .github/workflows/issue-pipeline.yml
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
jobs:
  pipeline:
    uses: abi83/interns/.github/workflows/code-pipeline.yml@v0.1.0
    secrets: inherit
    with:
      issue_number: ${{ inputs.issue_number }}
      pr_number: ${{ inputs.pr_number }}
      fix_round: ${{ inputs.fix_round || false }}
      phase: ${{ inputs.phase }}
```

Keep the `@v0.1.0` pin — the reusable cores check out their own matching assets
from that ref at runtime. Full stubs, including the `on:` triggers, are in
[`templates/workflows/`](templates/workflows).

Optionally add `.github/agent-pipeline.yml`
([template](templates/config/agent-pipeline.yml)) for per-agent limits, and the
default issue templates ([`templates/issue/`](templates/issue)) — pass
`--issue-templates` to the installer, or `install_issue_templates: true` to
`install.yml`.

## Troubleshooting

**A label change didn't start a run.** Label edits made by `GITHUB_TOKEN` (or
any action using it) don't trigger new workflow runs — GitHub's anti-recursion
rule. The `status:estimated` → `status:ready` approval must be a **human**
label edit for the coder to fire. The pipeline works around this internally by
dispatching the coder fix round with an explicit `workflow_dispatch` instead of
a label. To re-run a phase by hand, use the `workflow_dispatch` on the caller
workflow (`phase: refine|estimate` / `phase: coder|reviewer`).

**A fork PR got no review.** The reviewer job skips PRs from forks — forked
runs have no access to secrets, so the app token and OAuth token would be
empty. Review fork PRs manually. The same skip applies to bot PRs other than
the coder's `claude[bot]` (Dependabot, etc.).

**The installer's safety check failed.**

| Failure | Fix |
|---|---|
| `missing repo secret(s)` / `variable(s)` | add them (§2) — the installer can't set their values |
| `can't read branch protection … needs repo-admin scope` | pass an admin token as `install.yml`'s `admin_token` secret, or set protection by hand (§3) |
| `branch '…' push allowlist grants '…[bot]'` | remove that bot from the default branch's push restrictions |
| `GitHub Pages could not be enabled` | turn it on under Settings → Pages (build type: GitHub Actions) |

**An issue on `status:ready` bounced to `status:needs-attention`.** It reached
the coder without a `type:coding-task` or `type:bug` label — only those two are
implementable. Add the right type label and re-apply `status:ready`.

**A PR is stuck on `pr:needs-attention`.** One of: the `test` / `build` checks
went red (the coder is expected to push green — this goes straight to a human,
no retry), a second review round still requested changes (the fix loop didn't
converge), or the automatic-review cap (5 per PR) was hit. Read the PR comment
the pipeline left for which. Re-engage a reviewer with the caller's
`workflow_dispatch` (`phase: reviewer`, `pr_number: N`) once addressed.

**The coder declined a fix round.** It left a comment on the issue explaining
why (feedback needs a protected path, is out of scope, or needs an owner
decision) and set `status:needs-attention`. Pipeline config under
`.github/workflows/` and the `gh-safe` / `pipeline` scripts are protected —
`push-branch.sh` rejects any push touching them.

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
| `installer/` | `interns-install` — the local CLI for Apps + secrets (Python, stdlib only) |
| `install.sh` | one-line bootstrap: ensures `uv`, runs `interns-install` |

## License

MIT
