"""The step outputs of the plan job's commands: one routed job and its operands."""

from __future__ import annotations

from . import cli
from .domain.routing import Route


def write_route(route: Route) -> None:
    cli.write_output("job", route.job.value)
    cli.write_output("issue", "" if route.issue is None else str(route.issue))
    cli.write_output("pr", "" if route.pr is None else str(route.pr))
    cli.write_output("fix_round", route.fix_round)
    cli.write_output("skip_reason", route.skip_reason)
