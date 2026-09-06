# interns

A tireless team of interns that refine issues, estimate them, open PRs, and review each other's work — with a human in
the loop when really needed.

The pipeline drives [Claude Code](https://github.com/anthropics/claude-code) over a
checked-out repo, respects its `CLAUDE.md` / `AGENTS.md`, and runs entirely in the
host repo's GitHub Actions — no hosted service, no VMs to manage, no machine of your
own left running. Each issue and PR is its own workflow run, so the work fans out
concurrently and scales with your Actions runners, not with your attention.

Status: early. Consumed by [`abi83/prepify`](https://github.com/abi83/prepify).
Design and roadmap: [#3](https://github.com/abi83/interns/issues/3).

## What it does

Four agents pick issues up by label and hand them along a fixed track:

| Agent | Trigger                                                               | Does | Leaves |
|---|-----------------------------------------------------------------------|---|---|
| **Refiner** | `status:needs-refinement` on an issue                                 | picks the type, checks the draft against the codebase and wiki, rewrites the body into the type's template, posts a blockers/dependencies comment | `status:refined` |
| **Estimator** | `status:refined`                                                      | reads the code the Scope touches, scores blast radius / touch / human involvement / review overhead, rolls that into a size | `status:estimated` + `size:*` |
| **Coder** | `status:ready` (human-assigned) on a `type:coding-task` or `type:bug` | implements every Acceptance Criteria item, writes tests, opens a PR that `Closes #N` | `status:in-progress`, a PR labelled `pr:in-review` |
| **Reviewer** | a PR opened/updated by the coder (or a human)                         | waits for the PR's checks to be green, reviews the diff against the linked issue, submits `APPROVE` or `REQUEST_CHANGES` | PR approved, or a coder fix round, or `pr:needs-attention` |

The human owner steps in twice. First, on a refined and estimated issue: decide
whether to run the automated implementation flow, or send the task back for
rework — e.g. the scope is too broad to land in one PR, the estimator flagged a
huge blast radius, or refinement surfaced blockers and missing prerequisites.
Approving is a single move: the label `status:estimated` → `status:ready`.
Second, give the finished PR — already implemented and reviewer-approved — a
final look and merge it. Everything in between is automated, and
anything the automation can't finish — a Claude error, a vague issue
description, missing prerequisites or blockers — is parked on
`status:needs-attention` / `pr:needs-attention` for a human to pick up.

```mermaid
flowchart TD
    A([issue opened]) --> B

    subgraph P1 ["refine &amp; estimate · automated"]
        B["status:needs-refinement"] -->|refiner| C["status:refined"]
        C -->|estimator| D["status:estimated + size:*"]
    end

    D -->|owner approves| E

    subgraph P2 ["code &amp; review · automated"]
        E["status:ready"] -->|coder opens PR| F["pr:in-review"]
        F -->|REQUEST_CHANGES| G["pr:coding"]
        G -->|coder pushes a fix| F
    end

    F -->|APPROVE| H["PR approved"]
    H -->|owner merges| I([issue closed])

    P1 -.->|agent can't proceed| J["status:needs-attention"]
    P2 -.->|escalation| K["pr:needs-attention"]
```

## Label state machine

The installer syncs these from the versioned manifest
([`.github/labels.json`](.github/labels.json)). Label sync is additive — labels
not in the manifest are left alone.

### `status:*` — issue lifecycle (mutually exclusive)

| Label | Meaning                                                | Set by                                                                      | Moves to                                                                                                                                                                       |
|---|--------------------------------------------------------|-----------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `status:needs-refinement` | awaiting the refiner                                   | **human**, triggers the refinement-estimation pipeline                      | `status:refined`, or `status:needs-attention` if the refiner needs a decision                                                                                                  |
| `status:refined` | refined, awaiting estimation                           | refiner                                                                     | `status:estimated` (+ `size:*`); `status:needs-attention` if unsizeable                                                                                                       |
| `status:estimated` | estimated — waiting on the owner to approve or comment | estimator                                                                   | `status:ready` set by a human to trigger the coder, or a human **comment** to trigger conversational follow-up (TBD, [#11](https://github.com/abi83/interns/issues/11)). |
| `status:ready` | approved for the coder                                 | **human**, triggers the coder-reviewer pipeline                             | `status:in-progress` when the coder starts; `status:needs-attention` if the issue isn't a `type:coding-task` / `type:bug`                                                      |
| `status:in-progress` | a coder-reviewer loop is in progress                   | coder                                                                       | cleared when the PR merges (issue closed by `Closes #N`); `status:needs-attention` if the PR is closed unmerged, or on any pipeline stall                                        |
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

A red PR check also sends the PR straight to `pr:needs-attention`, with no fix
round.

| Label | Meaning                                      | Set by                      | Moves to |
|---|----------------------------------------------|-----------------------------|---|
| `pr:coding` | a coder agent is on this PR (e.g. fix round) | reviewer, when it requests changes | `pr:in-review` after the coder pushes |
| `pr:in-review` | a reviewer agent is on this PR               | coder, at hand-off          | cleared on `APPROVE`; `pr:coding` on `REQUEST_CHANGES`; `pr:needs-attention` on escalation |
| `pr:needs-attention` | PR pipeline stalled — a human needs to look  | reviewer gate               | cleared by the next agent run, once a human re-triggers the flow or pushes a commit |

An approved PR carries **no** `pr:*` label — the native review state is the
signal. List the PRs waiting on a human with
`gh pr list --label pr:needs-attention`.

### `type:*` — set by the refiner (or a human at creation), never changed after

| Label | Estimated? | Coder implements? |
|---|---|---|
| `type:coding-task` | yes | yes |
| `type:bug` | yes | yes |
| `type:spike` | yes | no — a human does the investigation |
| `type:epic` | no — refiner refuses it up front | no — a human breaks it into sub-issues |

Spikes and epics are never implemented automatically. A spike is refined and
estimated, then bounced to `status:needs-attention` at the coder's type gate. An
epic doesn't even get refined — the refiner refuses it. Either way, a human
takes it from there.

### `size:*` and `priority:*`

`size:XS` … `size:XL` are added by the estimator alongside `status:estimated`.
`priority:low` …
`priority:urgent` are owner triage labels — the pipeline reads neither; they
exist for humans sorting the backlog.

## Setup

From a local clone of your repo, with the [GitHub CLI](https://cli.github.com/)
authenticated (`gh auth login`) as an account with **admin access to the
repo** (needed to create repo secrets and variables):

```bash
curl -LsSf https://raw.githubusercontent.com/abi83/interns/v0.1.0/install.sh | sh
```

The script installs [`uv`](https://docs.astral.sh/uv/) if it's missing, then
runs the `interns-install` CLI. On a fresh repo you merge two small PRs it
opens (the install wrapper, then the caller stubs) and re-run it once in
between — see the steps below.

### What the installer does

`interns-install` runs the steps below, in order, then hands off to
`.github/workflows/install.yml` for the rest. Both halves are idempotent —
re-run either any time to fix drift.

| # | Step | Why |
|---|---|---|
| 1 | Check (and fix) default-branch protection | An agent could ignore its instructions and push straight to the default branch; protection forces every change through a PR. |
| 2 | Check (and enable) GitHub Pages | Deploy target for the visibility dashboard ([#6](https://github.com/abi83/interns/issues/6)). |
| 3 | Mint the two GitHub Apps | Separate coder/reviewer identities, so the reviewer can approve the coder's PRs (`claude[bot]` can't approve its own). |
| 4 | Write App secrets/variables + `CLAUDE_CODE_OAUTH_TOKEN` | The workflows need these to authenticate as the Apps and call Claude. |
| 5 | Hand off to `install.yml` | If no caller for it exists yet, open a one-file PR adding `.github/workflows/install.yml` (a thin wrapper) — merge it and re-run the installer. Once present, dispatch it. |
| 6 | (`install.yml`) Sync labels | The pipeline routes on `status:*` / `type:*` / `pr:*` and can't run without them. |
| 7 | (`install.yml`) Open the caller-stub PR | Adds the pipeline's workflows and starter config; merging it finishes setup. |

#### Default-branch protection

The agents push branches with your repo's own credentials, so no bot identity
(`github-actions[bot]`, `claude[bot]`, the two Apps) may be on the default
branch's push allowlist. By starting state:

| Default branch | Result |
|---|---|
| already requires a PR review, no bot on the push allowlist | passes |
| unprotected | installer applies the baseline — require a PR + 1 approval, no force-push, no deletion |
| protected, but your `gh` session lacks admin on the repo | **install fails** — re-auth with admin access, then re-run |
| a bot identity is on the push allowlist | **install fails** — remove it, then re-run |

If protection is enforced some other way this check can't see (an org-wide
ruleset, say), pass `interns-install --branch-protection-handled-externally`
to skip it.

#### GitHub Apps

`interns-coder` and `interns-reviewer`, minted via the App Manifest flow, one
"Create GitHub App" click each. Same permission set, no webhook:

| Permission | Access | Why |
|---|---|---|
| Contents | Read and write | push branches |
| Pull requests | Read and write | open PRs, submit reviews, comment |
| Issues | Read and write | edit labels, comment, rewrite the issue body (the refiner) |
| Checks | Read | reviewer reads check results |
| Metadata | Read | mandatory baseline |

Installing each App on the repo is a manual click — the installer prints the
links.

#### Secrets and variables

App keys and IDs come from the mint above; for `CLAUDE_CODE_OAUTH_TOKEN` the
installer prompts you to paste a token you obtain separately (see
`anthropics/claude-code-action`).

| Kind | Name | Value |
|---|---|---|
| Secret | `CLAUDE_CODE_OAUTH_TOKEN` | OAuth token for `anthropics/claude-code-action` |
| Secret | `INTERNS_CODER_APP_PRIVATE_KEY` | `interns-coder` private key (PEM) |
| Secret | `INTERNS_REVIEWER_APP_PRIVATE_KEY` | `interns-reviewer` private key (PEM) |
| Variable | `INTERNS_CODER_APP_ID` | `interns-coder` App ID |
| Variable | `INTERNS_REVIEWER_APP_ID` | `interns-reviewer` App ID |

The `install.yml` safety check fails the install if a required secret or
variable is missing; if its token can't list them it warns and leaves
verification to you.

#### Install wrapper

`install.yml` is a reusable workflow in `abi83/interns`; a consumer repo can
only invoke it through a local caller. When `interns-install` finds none, it
opens a one-file PR adding
[`.github/workflows/install.yml`](templates/workflows/install.yml) — a thin
`workflow_dispatch` wrapper pinned to `@v0.1.0`. Merge it (branch protection is
already on, so it can't be a direct push), then re-run `interns-install`; it
dispatches the wrapper and proceeds to the caller-stub PR.

#### Caller-stub PR

Adds two thin caller workflows that own the triggers and delegate to the
reusable cores, plus a starter `.github/interns.yml`. Adds only missing files,
never overwriting a hand-edited one; pinned to `@v0.1.0`. Merge it to finish.
Full stubs, including the `on:` triggers, are in
[`templates/workflows/`](templates/workflows).

Pass `--issue-templates` (or `install_issue_templates: true` to `install.yml`)
to also add the default issue templates
([`templates/issue/`](templates/issue)).

### Pipeline configuration

One source of truth: [`.github/interns.yml`](templates/config/interns.yml),
installed with every key already filled in at its default so you can see
what's configurable without reading the source. Edit it, or delete a key to
fall back to interns' own built-in default. A value can only come from this
file or the built-in — there is no second, overlapping source.

The reviewer waits for **all** of a PR's checks to be green before it runs — a
red or cancelled check on anything routes the PR to a human instead. Name any
non-blocking advisory checks (preview deploys, coverage deltas) under
`checks.ignore` in `.github/interns.yml` to keep them out of that gate.

### Doing it by hand

<details>
<summary>The manual path, without <code>interns-install</code></summary>

The fully manual path stays supported: create the two Apps with the permissions
above and install them on the repo, add the secrets and variables, set branch
protection, and commit the caller stubs from
[`templates/workflows/`](templates/workflows) yourself — including
[`install.yml`](templates/workflows/install.yml). With that wrapper in place,
run it (`gh workflow run install.yml`) to sync labels and open the caller-stub
PR, or sync labels from the manifest by hand.

</details>

## Troubleshooting

<details>
<summary><b>A label change didn't start a run.</b></summary>

Label edits made by `GITHUB_TOKEN` (or any action using it) don't trigger new
workflow runs — GitHub's anti-recursion rule. The `status:estimated` →
`status:ready` approval must be a **human** label edit for the coder to fire.
The pipeline works around this internally by dispatching the coder fix round
with an explicit `workflow_dispatch` instead of a label. To re-run a phase by
hand, use the `workflow_dispatch` on the caller workflow
(`phase: refine|estimate` / `phase: coder|reviewer`).

</details>

<details>
<summary><b>A fork PR got no review.</b></summary>

The reviewer job skips PRs from forks — forked runs have no access to secrets,
so the app token and OAuth token would be empty. Review fork PRs manually. The
same skip applies to bot PRs other than the coder's `claude[bot]`
(Dependabot, etc.).

</details>

<details>
<summary><b>The installer's safety check failed.</b></summary>

| Failure | Fix |
|---|---|
| `missing repo secret(s)` / `variable(s)` | add them (see Setup) — `install.yml` can't set their values |
| `can't read branch protection … needs admin access` | re-run `gh auth login` (or refresh your PAT) with admin access on the repo, then re-run `interns-install` |
| `branch '…' push allowlist grants '…[bot]'` | remove that bot from the default branch's push restrictions |
| `can't read GitHub Pages state … needs admin access` | same as above — `interns-install` needs an admin-scoped `gh` session |
| `GitHub Pages could not be enabled` | turn it on under Settings → Pages (build type: GitHub Actions) |

</details>

<details>
<summary><b>An issue on <code>status:ready</code> bounced to <code>status:needs-attention</code>.</b></summary>

It reached the coder without a `type:coding-task` or `type:bug` label — only
those two are implementable. Add the right type label and re-apply
`status:ready`.

</details>

<details>
<summary><b>A PR is stuck on <code>pr:needs-attention</code>.</b></summary>

One of: a PR check went red (the coder is expected to push green — this goes
straight to a human, no retry), a second review round still
requested changes (the fix loop didn't converge), or the automatic-review cap
(5 per PR) was hit. Read the PR comment the pipeline left for which. Re-engage a
reviewer with the caller's `workflow_dispatch` (`phase: reviewer`,
`pr_number: N`) once addressed.

</details>

<details>
<summary><b>The coder declined a fix round.</b></summary>

It left a comment on the issue explaining why (feedback needs a protected path,
is out of scope, or needs an owner decision) and set `status:needs-attention`.
Pipeline config under `.github/workflows/` and the `gh-safe` / `pipeline`
scripts are protected — `push-branch.sh` rejects any push touching them.

</details>

## Pipeline metrics

Every agent run appends one machine-readable record per `(run, job)` to
`metrics.jsonl` on an orphan `metrics` branch in your repo — tokens
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

## License

MIT
