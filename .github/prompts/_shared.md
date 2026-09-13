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
