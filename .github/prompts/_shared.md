## Reading issue data

The current issue's number, title, labels, body, and comments are already in
your prompt — use those directly. Do not call `gh` CLI or read
`$GITHUB_EVENT_PATH` to re-fetch them.

To look up *other* issues (blockers, cross-references), use
`mcp__gh-issues__view_issue` or `mcp__gh-issues__list_issues`. These are the
only sanctioned paths for reading issue data. Direct `gh` CLI calls are not in
the allowlist and will fail.

## `gh-safe` scripts

Every script under `.interns/.github/scripts/gh-safe/` resolves its own
target (the issue or PR bound to the triggering event) automatically, from
`$GITHUB_EVENT_PATH`. Never pass issue/PR body, title, comment, or review
text as a Bash argument — multi-line text breaks shell quoting. Write it to
the file the script expects (with the Write tool), then run the script with
no arguments:

| Script | Writes to | File |
|---|---|---|
| `comment-issue.sh` | issue comment | `./.issue-pipeline-comment.md` |
| `comment-pr.sh` | PR comment | `./.pr-comment.md` |
| `edit-issue-body.sh` | issue body | `./.issue-pipeline-body.md` |
| `edit-issue-title.sh` | issue title | `./.issue-pipeline-title.md` |
| `open-pr.sh` | PR title + body | `./.pr-title.txt`, `./.pr-body.md` |
| `submit-pr-review.sh` | review verdict (JSON) | `./.pr-review.json` |

`edit-issue-labels.sh` and `push-branch.sh` take no file — labels are CLI
flags (`--add-label X --remove-label Y`), and `push-branch.sh` reads the
already-committed git state.
