"""Hands an estimated issue straight to the coder when the consumer's
`auto_proceed` config enables its size, skipping the human `status:estimated`
-> `status:ready` approval. Only coder-implementable types proceed -- the
coder would otherwise bounce the issue to status:needs-attention.

Runs with the triage App token: a `status:ready` edit made with GITHUB_TOKEN
would not fire the coder workflow.
"""

from __future__ import annotations

from .. import cli, config, gh
from ..ctx import ActionsCtx
from ..domain import labels
from ..env_spec import EnvSpec

ENV_SPEC = EnvSpec.of()

CODER_TYPES = (labels.TYPE_CODING_TASK, labels.TYPE_BUG)


def proceed(repo: str, issue: int, auto_proceed: dict[str, bool]) -> str | None:
    """The size that was auto-approved, or None when the issue stays on
    status:estimated for a human."""
    current = labels.issue_labels(repo, issue)
    if labels.STATUS_ESTIMATED not in current:
        return None
    if not any(label in current for label in CODER_TYPES):
        return None
    size_label = labels.find_size_label(current)
    if size_label is None:
        return None
    size = size_label.removeprefix(labels.SIZE_PREFIX)
    if not auto_proceed[size]:
        return None
    labels.apply_transition(repo, issue, labels.Transition(add=[labels.STATUS_READY], remove=[labels.STATUS_ESTIMATED]))
    gh.issue_comment(
        repo, issue,
        f"Auto-approved for the coder: `auto_proceed.{size}` is enabled, so `{size_label}` issues "
        "skip the manual `status:estimated` → `status:ready` step.",
    )
    return size


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("auto-proceed")
    parser.add_argument("--issue", type=int, required=True)
    args = parser.parse_args(argv)

    config_path = ctx.config_path
    auto_proceed = config.auto_proceed_config(config.load_raw(config_path), config_path)
    size = proceed(ctx.repo, args.issue, auto_proceed)
    if size is None:
        print(f"Issue #{args.issue} stays on status:estimated — awaiting human approval.")
    else:
        print(f"Issue #{args.issue} auto-approved (size {size}).")
    return 0
