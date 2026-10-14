"""`run-agent` command: runs one agent phase through `claude -p` and leaves the
execution file (stream-json, one event per line) and the debug file for the later
report, metrics and upload steps.

Reads the prompt from INTERNS_AGENT_PROMPT, the GitHub token from GH_TOKEN.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .. import cli, execution
from ..domain import agent_run
from ..domain.agent_run import AgentRun


def _stream(command: list[str], env: dict[str, str], prompt: str, exec_file: Path, debug: bool) -> None:
    """Agent output reaches the job log only when debug is on: consumer repos can be public."""
    stderr = None if debug else subprocess.DEVNULL
    with subprocess.Popen(
        command, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr, text=True
    ) as proc:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(prompt)
        proc.stdin.close()
        with exec_file.open("w") as out:
            for line in proc.stdout:
                out.write(line)
                out.flush()
                if debug:
                    print(line, end="")


def main(argv: list[str]) -> int:
    parser = cli.build_parser("run-agent")
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-turns", type=int, required=True)
    parser.add_argument("--mcp-config", required=True)
    parser.add_argument("--tools", required=True)
    parser.add_argument("--allowed-tools", required=True)
    parser.add_argument("--disallowed-tools", default="")
    parser.add_argument("--add-dir", default="")
    parser.add_argument("--execution-file", required=True)
    parser.add_argument("--debug-file", required=True)
    parser.add_argument("--debug", choices=("true", "false"), required=True)
    args = parser.parse_args(argv)

    run = AgentRun(
        model=args.model,
        max_turns=args.max_turns,
        mcp_config=args.mcp_config,
        tools=args.tools,
        allowed_tools=args.allowed_tools,
        disallowed_tools=[tool for tool in args.disallowed_tools.split(",") if tool],
        add_dirs=[args.add_dir] if args.add_dir else [],
        debug_file=args.debug_file,
    )
    prompt = cli.require_env("INTERNS_AGENT_PROMPT")
    env = agent_run.build_env(os.environ, cli.require_env("GH_TOKEN"))
    exec_file = Path(args.execution_file)
    exec_file.touch()
    cli.write_output("execution_file", str(exec_file))
    cli.write_output("debug_file", args.debug_file)

    _stream(agent_run.build_command(run), env, prompt, exec_file, args.debug == "true")

    outcome = agent_run.evaluate(execution.events(str(exec_file)), run.max_turns)
    print(f"run-agent: {'success' if outcome.success else 'failed'}: {outcome.summary}", file=sys.stderr)
    return 0 if outcome.success else 1
