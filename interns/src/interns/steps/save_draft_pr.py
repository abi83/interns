"""Runs after the initial coder step failed (max turns, timeout, crash). The
agent may never have committed or pushed, so the pipeline saves whatever is in
the working tree as a draft PR rather than losing it with the runner.

The draft links the issue with `Refs`, not `Closes`: it is not a deliverable,
the reviewer skips drafts, and it must not count as the issue's PR.
"""

from __future__ import annotations

import re

from .. import cli, gh
from ..ctx import ActionsCtx
from ..domain import push

PIPELINE_DIR = ".interns"
CONVENTIONAL_SUBJECT_RE = r"^\w+(\([^)]*\))?!?: "


def draft_title(commit_type_hint: str, issue_title: str) -> str:
    if re.match(CONVENTIONAL_SUBJECT_RE, issue_title):
        return issue_title
    return f"{commit_type_hint} {issue_title}"


def draft_body(issue: int, run_url: str) -> str:
    return (
        "Unfinished automated attempt: the coder stopped before completing the issue, "
        "and the pipeline saved its working tree here. Expect missing pieces and failing checks.\n\n"
        f"Run: {run_url}\n\n"
        f"Refs #{issue}"
    )


def stage_unfinished_work(workspace: str, base: str) -> bool:
    """Replace the branch's commits with one staged change set against `base`,
    minus pipeline-owned and protected paths. False when nothing is left."""
    push.git(workspace, "reset", "--soft", base)
    push.git(workspace, "add", "-A", "--", ".", f":(exclude){PIPELINE_DIR}")
    staged = push.git(workspace, "diff", "--cached", "--name-only", base).splitlines()
    protected = [path for path in staged if re.search(push.PROTECTED_PATHS_RE, path)]
    if protected:
        push.git(workspace, "reset", "--quiet", base, "--", *protected)
    return len(staged) > len(protected)


def save_draft_pr(repo: str, workspace: str, issue: int, title: str, run_url: str) -> str | None:
    branch = push.unprotected_branch(workspace)
    if gh.pr_for_head(repo, branch) is not None:
        return None

    default, base = push.fork_point(repo, workspace)
    if not stage_unfinished_work(workspace, base):
        return None

    push.git(workspace, "commit", "--quiet", "-m", title)
    push.push_branch(repo, workspace)
    return gh.pr_create(repo, branch, default, title, draft_body(issue, run_url), draft=True)


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("save-draft-pr")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--issue-title", required=True)
    parser.add_argument("--commit-type-hint", required=True)
    args = parser.parse_args(argv)

    url = save_draft_pr(
        ctx.repo, ctx.workspace, args.issue,
        draft_title(args.commit_type_hint, args.issue_title), ctx.run_url(),
    )
    if url is None:
        print("Nothing to save, or the branch already has an open PR.")
        return 0
    print(f"Saved unfinished work as draft PR: {url}")
    cli.write_output("draft_pr_url", url)
    return 0
