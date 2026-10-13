"""`plan-review`: decides whether the reviewer job runs, writing `run_review`.

In order: the PR's checks must be green (a red one routes the PR to a human),
the PR must be a pipeline PR, its head must not already be reviewed, and an
event-triggered run must be under the automatic review cap. workflow_dispatch
is an explicit human override: it skips the check gate and the cap.
"""

from __future__ import annotations

from .. import cli, config, gh
from ..ctx import ActionsCtx
from ..domain import checks, plan, review_cap, verdict


def _checks_green(ctx: ActionsCtx, pr: int) -> bool:
    config_path = ctx.config_path
    cfg = config.checks_config(config.load_raw(config_path), config_path)
    ok, reason = checks.wait_for_checks(
        ctx.repo, pr, ctx.run_id, cfg.ignore,
        timeout=cfg.timeout_seconds, poll=cfg.poll_seconds, settle=cfg.settle_seconds,
    )
    if not ok:
        checks.route_red_checks(ctx.repo, pr, reason, run_url=ctx.run_url())
    return ok


def _under_review_cap(ctx: ActionsCtx, pr: int, review_count: int) -> bool:
    config_path = ctx.config_path
    loop = config.review_loop_config(config.load_raw(config_path), config_path)
    capped = review_cap.check_cap(
        ctx.repo, pr, ctx.reviewer_bot, loop.max_automatic_reviews, count=review_count, run_url=ctx.run_url(),
    )
    return not capped


def should_review(ctx: ActionsCtx, pr: int, *, author_login: str, author_type: str, coder_bot: str) -> bool:
    dispatched = ctx.event_name == "workflow_dispatch"
    if dispatched:
        print("Manual dispatch — skipping the check gate.")
    elif not _checks_green(ctx, pr):
        return False

    if plan.is_foreign_bot(author_login, author_type, coder_bot):
        print(f"PR author {author_login} isn't the coder's own App ({coder_bot}) — not a pipeline PR, skipping.")
        return False

    head_sha = gh.pr_view(ctx.repo, pr, ["headRefOid"])["headRefOid"]
    reviews = verdict.reviews_by(ctx.repo, pr, ctx.reviewer_bot)
    if verdict.verdict_for_head(reviews, head_sha) is not None:
        print(f"Head commit {head_sha} already reviewed — duplicate event, skipping.")
        return False

    return dispatched or _under_review_cap(ctx, pr, len(reviews))


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("plan-review")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--coder-bot", required=True)
    parser.add_argument("--pr-author-login", default="", help="empty on workflow_dispatch")
    parser.add_argument("--pr-author-type", default="", help="empty on workflow_dispatch")
    args = parser.parse_args(argv)

    run = should_review(
        ctx, args.pr, author_login=args.pr_author_login, author_type=args.pr_author_type, coder_bot=args.coder_bot,
    )
    cli.write_output("run_review", run)
    return 0
