"""`route-event`: maps the triggering GitHub event to the one job it starts.

Pure routing, no `gh` calls. The plan job runs it first so later steps (app
tokens, a config checkout) can be limited to the jobs that need them.
"""

from __future__ import annotations

from .. import cli, plan_outputs
from ..ctx import ActionsCtx
from ..domain import routing


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("route-event")
    parser.add_argument("--handles", required=True, help="comma-separated jobs the calling workflow runs")
    args = parser.parse_args(argv)

    route = routing.route(ctx.event(), routing.RouteConfig.parse(args.handles))
    if route.skip_reason:
        print(f"No job: {route.skip_reason}")
    plan_outputs.write_route(route)
    return 0
