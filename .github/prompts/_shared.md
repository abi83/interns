Conventions shared by every pipeline agent prompt. Referenced, not duplicated
— each prompt tells you to read this once alongside its own instructions.

## `gh-safe` scripts

Every script under `.interns/.github/scripts/gh-safe/` resolves its own
target (the issue or PR bound to the triggering event) automatically, from
`$GITHUB_EVENT_PATH`. No argument, environment variable, or script internals
to check first — just write the file the script expects (with the Write
tool) and run the script with no arguments.

Never pass issue/PR body, title, or comment text as a Bash argument —
multi-line markdown breaks shell quoting. The Write-file-then-run-script
pattern above is the only supported way to pass that content.
