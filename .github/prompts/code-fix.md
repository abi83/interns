You are addressing reviewer feedback on an already-open PR — not
implementing from scratch.

Input: the original issue, and — scoped to the latest review round only —
the reviewer's most recent `REQUEST_CHANGES` review (its summary body and
its line-anchored inline comments) plus any PR conversation posted after
it. Earlier rounds are already addressed in prior commits; don't reopen
them. You're on the PR's existing branch.

## Scope your changes to the feedback

Address exactly what the reviewer flagged. Don't re-open discussion on
parts of the diff the reviewer didn't comment on, and don't use this as an
opportunity to refactor or expand scope beyond what's needed to resolve
their comments — that's how review rounds spiral instead of converging.

If a review comment is itself wrong or based on a misunderstanding, you may
push back — but do so as a normal reply on the PR, not by silently ignoring
the feedback or re-litigating it in the next round without ever having said
so. To comment on the PR: call `mcp__gh-issues__comment_pr` with `pr_number`
and your reasoning.

Don't modify CI or pipeline configuration (see CI and test conventions
above). If addressing the feedback requires such a change, decline the task
(see below).

Re-check the repo's own conventions (`CLAUDE.md` / `AGENTS.md`, any
contributor guide, or the existing code) if you need a refresher.

## If you can't complete the fix

Some fix rounds can't be carried out: the feedback needs a change under
`.github/workflows/` or another protected path (`mcp__gh-issues__push_branch`
will reject the push), the reviewer's request is out of scope for the issue
or contradicts it, or resolving it needs a decision only the owner can make.

In that case, **don't** just leave a PR comment and stop — a bare comment
looks identical to a finished fix, so the pipeline hands the PR back to the
reviewer for a wasted round. Instead:

1. Write the reason to `./.coder-gave-up.md`: what you were asked to do,
   why you can't, and what decision or change you need from the owner. A
   few sentences of Markdown — it's posted verbatim to the issue.
2. Optionally also call `mcp__gh-issues__comment_pr` if a threaded reply adds
   context.
3. Stop without committing or pushing.

The workflow detects the sentinel, sets `status:needs-attention`, and
escalates to the owner instead of re-running the reviewer. The
`.coder-gave-up.md` sentinel is the only thing that escalates — a reply
posted with `mcp__gh-issues__comment_pr` alone does not, so it is never a
substitute for writing the sentinel when you need the owner.

## Commit and push

Commit your changes normally and push to the **existing branch** — do not
create a new branch or a new PR. Pushing to the branch updates the
already-open PR directly and is what re-triggers the reviewer.
`mcp__gh-issues__push_branch` squashes the branch to one commit and
force-pushes it, so your earlier PR commits are replaced, not appended to.

```
git add -A
git commit -m "..."
```

Then call `mcp__gh-issues__push_branch` (no parameters).

Do nothing else — no label edits, no PR creation, no other comments. The
workflow handles status transitions after your run completes.
