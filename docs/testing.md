# Testing

One runner (pytest + coverage), one root config ([pyproject.toml](../pyproject.toml)),
all three packages (`pipeline`, `installer`, `gh-issues-mcp`). Everything runs
from the repo root with no install step:

```sh
uv run --frozen python tools/test_unit.py         # unit tier
uv run --frozen python tools/test_integration.py  # integration tier
uv run --frozen ruff check .                      # unused imports / dead code
```

Extra arguments go to pytest (`... test_unit.py -k labels`).

## Tiers

| Tier | Where | What |
| --- | --- | --- |
| Unit | `pipeline/tests`, `installer/tests`, `.github/scripts/gh-issues-mcp/tests`, `tests/contract`, `tests/guards` | Pure logic, no process boundary. |
| Integration | `tests/integration` | Real entrypoint, real env/argv/`$GITHUB_OUTPUT`, through all real code to the process boundary, where `gh` and `git` are fake executables on `$PATH`. Assert on the calls issued, resulting labels and step outputs — not on internal calls. |

Coverage (branch) is measured per tier, and each command fails below its
floor, kept in `[tool.interns-tests.floors]` in `pyproject.toml`. A floor is
the measured number minus a small margin; raise it when coverage rises.

## Integration harness

`testkit/harness.py`. A `Scenario` installs fake `gh`/`git`
(`testkit/fake_cli.py`), records every call, and answers from canned rules:

```python
scenario.gh("pr", "view", "labels", stdout={"labels": [{"name": "pr:coding"}]})
result = scenario.run("pipeline.handoff_to_review", "7", "12")
assert scenario.label_edits("pr") == [("12", {"pr:in-review"}, {"pr:coding"})]
```

A rule matches a call containing all its tokens; the most specific rule wins,
then the newest. State-changing commands (`gh issue edit`, `git push`, …) succeed
silently; any other unmatched call fails the scenario. `Scenario.run` /
`run_tool` are the only places that know how an entrypoint is launched.

## Contract fixtures

`tests/contract/fixtures` holds raw output of the real `gh` for the calls the
code parses; `tests/contract/test_gh_contract.py` runs the parsing code on
them. Re-capture with `tests/contract/capture.py`.

## Guards (`tests/guards`)

- label manifest ↔ label constants in code
- config schema ↔ the config loader's known keys
- no new `except …: return <default>` in `pipeline` (existing sites are listed
  in the test)
