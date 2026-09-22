# Test guide

Before writing tests, read this.

## How to run

```sh
uv run --frozen python -m pytest interns/tests installer/tests mcp/tests  # unit tier
uv run --frozen python -m pytest tests/integration                         # integration tier
uv run --frozen python -m pytest tests/guards tests/contract               # guards + contracts
uv run --frozen ruff check .                                               # lint
```

## Tiers

**Unit** — pure logic, no process boundary. Test one function or module in isolation. Mock only at the system boundary (`gh`, `git`); don't mock internal collaborators.

**Integration** — real entrypoint, real env/argv/`$GITHUB_OUTPUT`, through all real code to the process boundary where `gh` and `git` are fake executables on `$PATH`. Assert on the calls issued, resulting labels and step outputs — not on internal state or intermediate calls.

**Guards** — structural invariants that must hold across the whole codebase: label manifest matches code constants, config schema matches loader, no new error-swallowing sites, import-direction rules.

**Contract fixtures** — raw `gh` output captured from the real API; parsing code is tested against it. Re-capture with `tests/contract/capture.py` when the `gh` output shape changes.

## Integration harness

`tests/testkit/harness.py`. A `Scenario` installs fake `gh`/`git`, records every call, and answers from canned rules:

```python
scenario.gh("pr", "view", "labels", stdout={"labels": [{"name": "pr:coding"}]})
result = scenario.run("interns.steps.handoff_to_review", "7", "12")
assert scenario.label_edits("pr") == [("12", {"pr:in-review"}, {"pr:coding"})]
```

A rule matches a call containing all its tokens; the most specific rule wins, then the newest. State-changing commands succeed silently; any unmatched call fails the scenario. `Scenario.run` / `run_tool` are the only places that know how an entrypoint is launched.
