## CI and test conventions

Don't modify CI or pipeline configuration — anything under
`.github/workflows/`, or the paths `mcp__gh-issues__push_branch` rejects.
That tool rejects any push that touches those paths.

Run `make test` and `make build` and keep them green before pushing. If the
repo has no `Makefile`, or the output says `INTERNS: not configured`,
testing isn't set up for this repo yet — that's expected, not a failure.
Don't try to configure it yourself unless explicitly asked to; just note it
didn't run and move on. A red check sends the issue straight to a human
instead of back to you, so don't push a failing build or failing tests that
aren't the `INTERNS: not configured` stub.
