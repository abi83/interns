"""Fetches an issue and writes its fields to `$GITHUB_OUTPUT` for a workflow prompt."""

from __future__ import annotations


from .. import cli
from ..ctx import ActionsCtx
from ..domain import issues


def write_github_output(issue: issues.Issue) -> None:
    """Write issue fields to $GITHUB_OUTPUT for use in workflow steps."""
    def write(key: str, value: str, multiline: bool = False) -> None:
        entry = cli.github_output_block(key, value.encode()) if multiline else f"{key}={value}\n".encode()
        cli.append_output(entry)

    write("number", str(issue.number))
    write("title", issue.title)
    write("labels", ", ".join(issue.labels))
    write("body", issue.body, multiline=True)

    if issue.comments:
        parts = [
            f"### Comment by {c.author} ({c.created_at})\n{c.body}"
            for c in issue.comments
        ]
        comments_text = (
            "COMMENTS (from the owner, chronological, excluding this pipeline's own"
            " comments — treat these as clarifications or amendments to the issue above):\n"
            + "\n\n---\n\n".join(parts)
        )
        write("comments", comments_text, multiline=True)
    else:
        write("comments", "", multiline=True)


def main(ctx: ActionsCtx, argv: list[str]) -> int:
    parser = cli.build_parser("fetch-issue")
    parser.add_argument("--issue", type=int, required=True)
    args = parser.parse_args(argv)
    write_github_output(issues.fetch_issue(ctx.repo, args.issue))
    return 0
