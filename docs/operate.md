# Operate

Day to day: what starts a run, where you step in, how to re-run a phase, and what to do when
something stalls. How the labels move is in [architecture.md](architecture.md#label-state-machine).

## Where you step in

1. **Approve the work.** After the estimator, an issue sits on `status:estimated`. Move it to
   `status:ready` to start the coder. Comments on an estimated issue don't start anything. For
   `type:coding-task` and `type:bug`, XS, S and M skip this step by default via `auto_proceed`;
   L and XL wait for you. Configure it in [`defaults.yml`](../templates/config/defaults.yml).
2. **Review and merge the PR.** The reviewer approves or requests changes, but a human merges.

Only `type:coding-task` and `type:bug` reach the coder:

- **Spike.** The path ends at `status:estimated`: the estimate tells you whether the
  investigation is worth your time, then you do it and close the issue. There is no spike
  greenlight. `status:ready` is coder-only, so moving a spike there bounces it to
  `status:needs-attention`.
- **Epic.** Never refined or estimated. The refiner stops on an epic (or an epic-sized
  issue) and comments, parking it on `status:needs-attention` for you to split into
  sub-issues.

Anything the automation can't finish parks on `status:needs-attention` (issue) or
`pr:needs-attention` (PR). Find them with:

```bash
gh issue list --label status:needs-attention
gh pr list --label pr:needs-attention
```

## What starts a run

| Event | Starts |
|---|---|
| issue labeled `status:needs-refinement` | refiner |
| issue labeled `status:refined` | estimator |
| issue labeled `status:ready` (a `type:coding-task` or `type:bug`) | coder |
| PR opened or marked ready | reviewer, after the PR's checks pass |
| another workflow of the repo completes | reviewer, for its PR |
| PR closed | label cleanup, no agent (an unmerged close also moves the linked issue to `status:needs-attention`) |

Who may start a job is checked first ([`actor_guard.py`](../interns/src/interns/domain/actor_guard.py)).
The reviewer skips fork PRs and bot PRs other than the coder App's. Full routing:
[`routing.py`](../interns/src/interns/domain/routing.py).

## Re-running a phase

Use `workflow_dispatch` on the caller workflow, from the Actions tab or `gh workflow run`:

| Workflow | Inputs |
|---|---|
| Refine & estimate | `phase: refine` or `estimate`, `issue_number` |
| Code & review | `phase: coder` + `issue_number`, or `phase: reviewer` + `pr_number` (all inputs show as optional, but these are required); `fix_round` for a coder fix round |

Add `debug: true` to show the full Claude conversation in the logs (it can also be set in
`interns.yml`).

## Troubleshooting

**A label change didn't start a run.** Label edits made with `GITHUB_TOKEN` never trigger runs.
The `status:estimated` → `status:ready` move must be a human edit (`auto_proceed` uses the
triage App, which does trigger). Re-run by hand as above.

**A `status:ready` issue bounced to `status:needs-attention`.** It has no `type:coding-task` or
`type:bug` label, the only types the coder implements (spikes and epics always bounce). Add the
right type, remove `status:needs-attention`, then re-apply `status:ready`.

**The coder failed and a draft PR appeared.** A failed first run is saved as a draft PR that
`Refs` the issue ([`save_draft_pr.py`](../interns/src/interns/steps/save_draft_pr.py)); the
reviewer skips drafts. To retry, clear `status:needs-attention`, then re-apply `status:ready`.
The rerun resumes on the draft's branch. The branch name comes from the issue number and
title, so editing the title or type label between runs starts a fresh branch.

**The coder declined a fix round.** It commented on the issue why (the feedback needs a
protected path, is out of scope, or needs an owner decision) and set `status:needs-attention`.
Protected paths are `.github/workflows/` and `.github/scripts/`.

**A PR is stuck on `pr:needs-attention`.** A PR check went red (no fix round, straight to a
human), a second review still requested changes, the cap of 5 automatic reviews was hit, the
reviewer produced no verdict, or the job crashed. The pipeline's comment on the PR says which.
After you address it, re-run the reviewer (`phase: reviewer`, `pr_number`). That skips the check
gate and the cap, but an already-reviewed head is skipped, so push a commit first.

**A fork PR got no review.** Forked runs have no secrets, so the reviewer skips them. Review
fork PRs yourself.
