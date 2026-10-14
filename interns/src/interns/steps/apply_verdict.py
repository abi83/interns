"""Acts on the reviewer's latest verdict on a PR.

Issue status:* is coarse: status:in-progress for the whole run,
status:needs-attention when a human is needed, closed on merge. There is no
"approved" issue state -- an approved PR is found via its native review
state, and the pr:* label only marks which agent is currently working (none,
once the reviewer is done) or pr:needs-attention when the loop has given up.
The fix-round decision is read from the verdict, not a label.
"""

from __future__ import annotations

from .. import cli, config, gh
from ..ctx import ActionsCtx
from ..domain import lifecycle, lifecycle_apply, verdict
from ..domain.verdict import ReviewState
from ..env_spec import EnvSpec

ENV_SPEC = EnvSpec.of("GITHUB_RUN_ID", "REVIEWER_BOT")


def _event(verdict_state: ReviewState | None) -> lifecycle.Event:
    match verdict_state:
        case ReviewState.APPROVED:
            return lifecycle.Event.APPROVED
        case ReviewState.CHANGES_REQUESTED:
            return lifecycle.Event.CHANGES_REQUESTED
        case _:
            return lifecycle.Event.NO_VERDICT


def apply_verdict(repo: str, pr: int, issue: int | None, reviewer_bot: str, *, max_fix_rounds: int, server_url: str = "", run_url: str = "") -> None:
    head_sha = gh.pr_view(repo, pr, ["headRefOid"])["headRefOid"]
    reviews = verdict.reviews_by(repo, pr, reviewer_bot)
    last_state = verdict.verdict_for_head(reviews, head_sha)

    rounds = verdict.rounds_requested(reviews)
    facts = lifecycle.Facts(has_issue=issue is not None, has_pr=True, fix_rounds=rounds, max_fix_rounds=max_fix_rounds)
    outcome = lifecycle.decide(_event(last_state), facts)
    lifecycle_apply.apply(repo, outcome, pr=pr, issue=issue, words=lifecycle_apply.Words(run_url=run_url, server_url=server_url))


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("apply-verdict")
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--issue", default="")
    args = parser.parse_args(argv)

    config_path = ctx.config_path
    rl = config.review_loop_config(config.load_raw(config_path), config_path)

    apply_verdict(
        ctx.repo,
        args.pr,
        cli.optional_int(args.issue),
        ctx.reviewer_bot,
        max_fix_rounds=rl.max_fix_rounds,
        server_url=ctx.server_url,
        run_url=ctx.run_url(),
    )
    return 0
