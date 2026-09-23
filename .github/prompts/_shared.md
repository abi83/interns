## Reading issue data

The current issue's number, title, labels, body, and comments are already in
your prompt — use those directly.

To look up *other* issues (blockers, cross-references), use
`mcp__gh-issues__view_issue` or `mcp__gh-issues__list_issues`.

## MCP tools for writing

All GitHub writes go through the `gh-issues` MCP server. Pass text directly
as tool parameters — no file-writing step required. The table below covers
the general-purpose tools; phase-specific outcome tools are listed in your
agent's own instructions below.

| Tool | What it does |
|---|---|
| `mcp__gh-issues__comment_issue` | Post a comment on an issue |
| `mcp__gh-issues__edit_issue` | Set the body (and optionally title) of an issue |
| `mcp__gh-issues__edit_issue_labels` | Add or remove labels on an issue |
| `mcp__gh-issues__comment_pr` | Post a comment on a PR |
| `mcp__gh-issues__open_pr` | Open a PR from the current branch |
| `mcp__gh-issues__submit_pr_review` | Submit a formal PR review (APPROVE / REQUEST_CHANGES) |
| `mcp__gh-issues__push_branch` | Squash the branch to one commit and push to origin |

All tools take explicit `issue_number` or `pr_number` parameters — the
numbers are in your prompt. `open_pr` appends `Closes #N` automatically; do
not add it yourself. `push_branch` takes no arguments — it reads the current
git state.
