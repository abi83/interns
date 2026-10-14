"""`confirm-route`: routes the event, then checks the routed job should really run.

The final `job` is `none` (with the reason) when a gate rejects the run:

- every agent job: an actor behind the event (for a workflow run, the upstream
  run's too) is neither a user with write access nor a pipeline identity.
  Checked first, before any gate that writes to the issue.
- coder: the issue type is not implementable, or the trigger is stale. A fix
  round is dispatched against an already `status:in-progress` issue, so it
  bypasses both.
- estimate: the issue is a type that can't be sized (an epic).
- reviewer: PR checks are red (the PR is routed to a human) or still running
  (no failure: the next completing workflow run triggers the review again), the
  PR isn't a pipeline PR, its head is already reviewed, or the automatic review
  cap is reached. workflow_dispatch is an explicit human override: it skips the
  check gate and the cap.

A workflow run event carries no draft flag or author, so its PR is fetched and
routed again as a pull request event.
"""

from __future__ import annotations

from dataclasses import replace

from .. import cli, config, gh, plan_outputs
from ..ctx import ActionsCtx
from ..domain import actor_guard, checks, labels, plan, review_cap, routing, type_gate, verdict
from ..domain.routing import Job, Route
from ..env_spec import EnvSpec


def _handles(argv: list[str]) -> list[str]:
    parser = cli.build_parser("confirm-route")
    parser.add_argument("--handles", required=True)
    args, _ = parser.parse_known_args(argv)
    return args.handles.split(",")


ENV_SPEC = EnvSpec(
    always=frozenset({"GITHUB_EVENT_NAME", "GITHUB_EVENT_PATH"}),
    by_phase={"reviewer": frozenset({"GITHUB_RUN_ID", "REVIEWER_BOT", "CODER_BOT"})},
    phases=_handles,
)

CODER_TYPES = [labels.TYPE_CODING_TASK, labels.TYPE_BUG]
CODER_REJECT_COMMENT = (
    "This issue reached `status:ready` without a `type:coding-task` or "
    "`type:bug` label, so the coder agent won't attempt it — only those "
    "two types are implementable code deliverables. If this should be "
    "implemented, add the correct type label and re-apply `status:ready`."
)
ESTIMATE_TYPES = [labels.TYPE_CODING_TASK, labels.TYPE_BUG, labels.TYPE_SPIKE]
ESTIMATE_REJECT_COMMENT = (
    "Epics aren't sized directly — a dev-effort number doesn't mean "
    "anything before the work is broken down. Break this into sub-issues "
    "and estimate those."
)


def _issue(route: Route) -> int:
    if route.issue is None:
        raise ValueError(f"{route.job} route has no issue")
    return route.issue


def _pr(route: Route) -> int:
    if route.pr is None:
        raise ValueError(f"{route.job} route has no PR")
    return route.pr


def _coder_skip_reason(repo: str, route: Route) -> str:
    issue = _issue(route)
    if route.fix_round:
        return ""
    if not type_gate.gate(repo, issue, CODER_TYPES, labels.STATUS_READY, CODER_REJECT_COMMENT):
        return f"issue #{issue} is not an implementable type"
    current = labels.issue_labels(repo, issue)
    if plan.is_stale_trigger(current):
        return f"issue #{issue} is already past status:ready ({', '.join(current)}): stale or duplicate trigger"
    return ""


def _estimate_skip_reason(repo: str, route: Route) -> str:
    issue = _issue(route)
    if not type_gate.gate(repo, issue, ESTIMATE_TYPES, labels.STATUS_REFINED, ESTIMATE_REJECT_COMMENT):
        return f"issue #{issue} is not an estimable type"
    return ""


def _checks_skip_reason(ctx: ActionsCtx, pr: int) -> str:
    config_path = ctx.config_path
    cfg = config.checks_config(config.load_raw(config_path), config_path)
    outcome, reason = checks.wait_for_checks(
        ctx.repo, pr, ctx.run_id, cfg.ignore,
        timeout=cfg.timeout_seconds, poll=cfg.poll_seconds, settle=cfg.settle_seconds,
    )
    if outcome is checks.Outcome.GREEN:
        return ""
    if outcome is checks.Outcome.PENDING:
        return reason
    checks.route_red_checks(ctx.repo, pr, reason, run_url=ctx.run_url())
    return f"checks are not green: {reason}"


def _review_cap_reached(ctx: ActionsCtx, pr: int, review_count: int) -> bool:
    config_path = ctx.config_path
    loop = config.review_loop_config(config.load_raw(config_path), config_path)
    return review_cap.check_cap(
        ctx.repo, pr, ctx.reviewer_bot, loop.max_automatic_reviews, count=review_count, run_url=ctx.run_url(),
    )


def _is_push_rereview(event: routing.GithubEvent, trigger: config.ReviewerTrigger, reviews: list[verdict.FullReview]) -> bool:
    # A finished workflow run replaces the old synchronize trigger; one for an already reviewed PR is a push.
    return isinstance(event, routing.PullRequestEvent) and event.action == "completed" and bool(reviews) \
        and not trigger.rereview_on_push


def _reviewer_skip_reason(
    ctx: ActionsCtx, event: routing.GithubEvent, route: Route, trigger: config.ReviewerTrigger,
) -> str:
    pr = _pr(route)
    dispatched = isinstance(event, routing.Dispatch)
    if not dispatched:
        reason = _checks_skip_reason(ctx, pr)
        if reason:
            return reason

    if isinstance(event, routing.PullRequestEvent):
        coder_bot = cli.require_env("CODER_BOT")
        if plan.is_foreign_bot(event.author_login, event.author_type, coder_bot):
            return f"PR author {event.author_login} isn't the coder's own App ({coder_bot}): not a pipeline PR"

    head_sha = gh.pr_view(ctx.repo, pr, ["headRefOid"])["headRefOid"]
    reviews = verdict.reviews_by(ctx.repo, pr, ctx.reviewer_bot)
    if verdict.verdict_for_head(reviews, head_sha) is not None:
        return f"head commit {head_sha} is already reviewed: duplicate event"

    if _is_push_rereview(event, trigger, reviews):
        return "PR already reviewed and agents.reviewer.trigger.rereview_on_push is false"

    if not dispatched and _review_cap_reached(ctx, pr, len(reviews)):
        return "automatic review cap reached"
    return ""


def _live_review_target(
    ctx: ActionsCtx, event: routing.WorkflowRunEvent, route: Route, config: routing.RouteConfig,
) -> tuple[routing.GithubEvent, Route]:
    pr = _pr(route)
    live = gh.pr_rest(ctx.repo, pr)
    if live["state"] != "open":
        return event, Route(Job.NONE, pr=pr, skip_reason="PR is not open")
    if live["head"]["sha"] != event.head_sha:
        return event, Route(Job.NONE, pr=pr, skip_reason="PR head moved past this workflow run")
    live_event = routing.pull_request_event("completed", live)
    return live_event, routing.route(live_event, config)


GUARDED_JOBS = frozenset({Job.REFINE, Job.ESTIMATE, Job.CODER, Job.REVIEWER})


def _actor_refusal(ctx: ActionsCtx, route: Route) -> str:
    if route.job not in GUARDED_JOBS:
        return ""
    return actor_guard.refusal(ctx.repo, ctx.actors())


def _skip_reason(ctx: ActionsCtx, event: routing.GithubEvent, route: Route, trigger: config.ReviewerTrigger) -> str:
    match route.job:
        case Job.CODER:
            return _coder_skip_reason(ctx.repo, route)
        case Job.ESTIMATE:
            return _estimate_skip_reason(ctx.repo, route)
        case Job.REVIEWER:
            return _reviewer_skip_reason(ctx, event, route, trigger)
        case _:
            return ""


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("confirm-route")
    parser.add_argument("--handles", required=True, help="comma-separated jobs the calling workflow runs")
    args = parser.parse_args(argv)

    event = ctx.event()
    route_config = ctx.route_config(args.handles)
    route = routing.route(event, route_config)
    reason = _actor_refusal(ctx, route)
    if not reason and isinstance(event, routing.WorkflowRunEvent) and route.job is Job.REVIEWER:
        event, route = _live_review_target(ctx, event, route, route_config)
    reason = reason or _skip_reason(ctx, event, route, route_config.trigger)
    final = replace(route, job=Job.NONE, skip_reason=reason) if reason else route
    if final.skip_reason:
        print(f"No job: {final.skip_reason}")
    plan_outputs.write_route(final)
    return 0
