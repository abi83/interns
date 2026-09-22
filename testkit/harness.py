"""Fake-`gh`/`git` harness for integration tests.

    scenario = Scenario(tmp_path)
    scenario.gh("pr", "view", stdout='{"labels": []}')     # canned response
    result = scenario.run("pipeline.apply_verdict", "7", "5")
    assert scenario.pr_label_edits() == [...]

Entrypoints run as real subprocesses with a real env, argv and
$GITHUB_OUTPUT; only `gh` and `git` are fakes (testkit/fake_cli.py).
`Scenario.run` and `Scenario.run_tool` are the only places that know how an
entrypoint is launched.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.ctx import ActionsCtx

ROOT = Path(__file__).resolve().parents[1]
FAKE_CLI = Path(__file__).with_name("fake_cli.py")
MCP_TOOL = Path(__file__).with_name("mcp_tool.py")
PYTHONPATH = [ROOT / "pipeline/src", ROOT / "installer/src", ROOT / ".github/scripts/gh-issues-mcp"]

REPO = "acme/widgets"


def default_ctx(**overrides) -> ActionsCtx:
    defaults: dict = dict(
        repo=REPO,
        token="",
        server_url="",
        run_id="",
        run_attempt=1,
        workspace=".",
        event_name="",
        reviewer_bot="",
        step_summary="",
    )
    defaults.update(overrides)
    return ActionsCtx(**defaults)


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str
    outputs: dict[str, str] = field(default_factory=dict)


def _parse_github_output(text: str) -> dict[str, str]:
    outputs: dict[str, str] = {}
    lines = iter(text.splitlines())
    for line in lines:
        if "<<" in line:
            key, delimiter = line.split("<<", 1)
            body = []
            for body_line in lines:
                if body_line == delimiter:
                    break
                body.append(body_line)
            outputs[key] = "\n".join(body)
        elif "=" in line:
            key, value = line.split("=", 1)
            outputs[key] = value
    return outputs


class Scenario:
    def __init__(self, tmp_path: Path):
        self.dir = tmp_path
        self.state = tmp_path / "fake-cli"
        self.workspace = tmp_path / "workspace"
        self.github_output = tmp_path / "github_output"
        self._rules: list[dict] = []

        bin_dir = tmp_path / "bin"
        for directory in (self.state, self.workspace, bin_dir):
            directory.mkdir()
        self.github_output.touch()
        for tool in ("gh", "git"):
            launcher = bin_dir / tool
            launcher.write_text(f"#!/bin/sh\nexec '{sys.executable}' '{FAKE_CLI}' {tool} \"$@\"\n")
            launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
        self._write_rules()
        self.env = {
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "PYTHONPATH": os.pathsep.join(map(str, PYTHONPATH)),
            "FAKE_CLI_DIR": str(self.state),
            "GITHUB_REPOSITORY": REPO,
            "GITHUB_SERVER_URL": "https://github.example",
            "GITHUB_RUN_ID": "4242",
            "GITHUB_OUTPUT": str(self.github_output),
            "GITHUB_WORKSPACE": str(self.workspace),
            "REVIEWER_BOT": "reviewer-bot",
            "GH_TOKEN": "fake-token",
            "HOME": str(tmp_path),
            **{k: v for k, v in os.environ.items() if k == "COVERAGE_FILE"},
        }

    def _canned(self, tool: str, args: tuple[str, ...], stdout: str | object, stderr: str, code: int) -> None:
        text = stdout if isinstance(stdout, str) else json.dumps(stdout)
        self._rules.insert(0, {"tool": tool, "args": list(args), "stdout": text, "stderr": stderr, "code": code})
        self._write_rules()

    def _write_rules(self) -> None:
        (self.state / "rules.json").write_text(json.dumps(self._rules))

    def gh(self, *args: str, stdout: str | object = "", stderr: str = "", code: int = 0) -> None:
        """Answer any `gh` call containing all of `args` (the most specific
        matching rule wins, then the newest). A non-string `stdout` is JSON-encoded."""
        self._canned("gh", args, stdout, stderr, code)

    def git(self, *args: str, stdout: str = "", stderr: str = "", code: int = 0) -> None:
        self._canned("git", args, stdout, stderr, code)

    def activate(self, monkeypatch) -> None:
        """Put the fakes on this process's own PATH, for tests that call
        library code in-process instead of an entrypoint."""
        monkeypatch.setenv("PATH", self.env["PATH"])
        monkeypatch.setenv("FAKE_CLI_DIR", self.env["FAKE_CLI_DIR"])

    def _launch(self, command: list[str], env: dict[str, str] | None) -> Result:
        if os.environ.get("INTERNS_COVERAGE"):
            sources = ",".join(str(path) for path in PYTHONPATH)  # absolute: the config's are relative to ROOT
            command = [sys.executable, "-m", "coverage", "run", "--rcfile", str(ROOT / "pyproject.toml"),
                       f"--source={sources}", *command[1:]]
        proc = subprocess.run(command, cwd=self.workspace, env={**self.env, **(env or {})},
                              capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assert_all_matched()
        return Result(proc.returncode, proc.stdout, proc.stderr, _parse_github_output(self.github_output.read_text()))

    def run(self, module: str, *args: str, env: dict[str, str] | None = None) -> Result:
        """Run `python -m <module> <args>`."""
        return self._launch([sys.executable, "-m", module, *args], env)

    def run_tool(self, name: str, env: dict[str, str] | None = None, **kwargs) -> Result:
        """Call a gh-issues MCP tool with `kwargs`."""
        return self._launch([sys.executable, str(MCP_TOOL), name, json.dumps(kwargs)], env)

    def _recorded(self) -> list[dict]:
        path = self.state / "calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def assert_all_matched(self) -> None:
        """Fail on any call that had no canned response, even if the code
        under test swallowed the resulting error."""
        unmatched = [c for c in self._recorded() if c["unmatched"]]
        assert not unmatched, f"calls with no canned response: {[[c['tool'], *c['argv']] for c in unmatched]}"

    def calls(self, tool: str, *prefix: str) -> list[list[str]]:
        """argv of every recorded `tool` call starting with `prefix`, in order."""
        return [c["argv"] for c in self._recorded() if c["tool"] == tool and c["argv"][: len(prefix)] == list(prefix)]

    def stdin_of(self, tool: str, *prefix: str) -> str:
        """stdin of the last matching call (only `gh api --input -` receives any)."""
        matching = [c for c in self._recorded() if c["tool"] == tool and c["argv"][: len(prefix)] == list(prefix)]
        assert matching, f"no recorded {tool} call starting with {list(prefix)}"
        return matching[-1]["stdin"]

    def label_edits(self, kind: str) -> list[tuple[str, set[str], set[str]]]:
        """(number, added, removed) for each `gh <kind> edit`."""
        edits = []
        for argv in self.calls("gh", kind, "edit"):
            added = {argv[i + 1] for i, a in enumerate(argv) if a == "--add-label"}
            removed = {argv[i + 1] for i, a in enumerate(argv) if a == "--remove-label"}
            edits.append((argv[2], added, removed))
        return edits

    def comments(self, kind: str) -> list[tuple[str, str]]:
        """(number, body) for each `gh <kind> comment`."""
        return [(argv[2], argv[argv.index("--body") + 1]) for argv in self.calls("gh", kind, "comment")]


def labels_payload(*names: str) -> dict:
    return {"labels": [{"name": name} for name in names]}
