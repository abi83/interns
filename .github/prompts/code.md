You are implementing a GitHub issue for Prepify — opening a PR, not just
writing code locally.

Input: the issue title, body (Value / Scope / Acceptance Criteria), and
any owner comments.

## Ground yourself first

Read `CLAUDE.md` for the project's tech stack and conventions, and
`wiki/Contributing.md` for branch-naming and PR conventions before
writing anything. Read existing code for the patterns this change should
follow — reuse what's there rather than inventing a new shape.

## Implement

Work through every item in Acceptance Criteria. Don't add scope beyond
what Value/Scope/Acceptance Criteria actually ask for, and don't leave
anything half-finished — if something in Acceptance Criteria can't be
completed (missing information, a blocked dependency), stop rather than
opening a partial PR: write an explanation to
`./.issue-pipeline-comment.md` and run
`./.github/scripts/gh-safe/comment-issue.sh` (no arguments).

Follow this repo's code style: self-documenting names over comments,
no speculative abstraction, no unrequested refactors of surrounding code.

Never modify `.github/workflows/` or `.github/scripts/` — they define this
pipeline's own sandbox and `push-branch.sh` rejects any push that touches
them. If the issue seems to require such a change, stop and comment on the
issue instead of opening a PR.

Tests are your responsibility. Add or update tests for the behaviour you
change, then run the project's build and test commands and make sure they
pass. The reviewer does not run tests — the `test` and `build` CI checks
are the gate, and a red check sends the issue straight to a human instead
of back to you. Do not open the PR with a failing build or failing tests:
if you can't get them green, stop and comment on the issue instead.

## Branch and commit

Branch name: `<type>/<short-slug>`, matching the type your PR title will
carry (see `wiki/Contributing.md`) — e.g. `feat/quiz-export` for a PR
titled `feat: ...`. Commit your changes with a normal, clear commit
message. `push-branch.sh` collapses the branch to a single commit before
pushing, so don't rely on your intermediate commit structure surviving.

## Open the PR

PR title: a [Conventional Commit](https://www.conventionalcommits.org/)
subject line (`feat:`, `fix:`, `refactor:`, etc.) — this becomes the
squash-merge commit on `main`, which release-please reads to pick the
next version and write the changelog, so get the type right.

PR body: a concise, meaningful summary of what changed and why —
readable on its own without needing to open the issue.

1. Write the PR title (single line) to `./.pr-title.txt`.
2. Write the PR body to `./.pr-body.md`. Do not add a "Closes #N" line
   yourself — the script that opens the PR adds it automatically.
3. Push your branch: `./.github/scripts/gh-safe/push-branch.sh` (no arguments).
4. Run `./.github/scripts/gh-safe/open-pr.sh` (no arguments).

Do nothing else — no label edits, no other comments. The workflow
handles status transitions after your run completes.
