"""`route-event`: maps the triggering GitHub event to the one job it starts.

Routing only, no `gh` calls. The plan job runs it first so later steps (app
tokens, the consumer checkout) can be limited to the jobs that need them. The
consumer's `.github/interns.yml` isn't checked out yet, so the reviewer trigger
policy is still the shipped default here; `confirm-route` applies the real one.
"""

from __future__ import annotations

from .. import cli, plan_outputs
from ..ctx import ActionsCtx
from ..domain import routing
from ..env_spec import EnvSpec

ENV_SPEC = EnvSpec.of("GITHUB_EVENT_NAME", "GITHUB_EVENT_PATH")


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("route-event")
    parser.add_argument("--handles", required=True, help="comma-separated jobs the calling workflow runs")
    args = parser.parse_args(argv)

    route = routing.route(ctx.event(), ctx.route_config(args.handles))
    if route.skip_reason:
        print(f"No job: {route.skip_reason}")
    plan_outputs.write_route(route)
    return 0
