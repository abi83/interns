"""Re-captures tests/contract/fixtures from the real `gh` CLI.

    uv run --frozen python tests/contract/capture.py <owner/repo> <pr> <issue>

Run against a repo with a merged PR that has a review, a linked issue and CI
checks. Each fixture is `gh`'s raw stdout for the exact call the pipeline
makes, so a shape change in `gh` (or a wrong assumption in our parsing, as in
`gh repo view --json owner`) fails a contract test instead of a live run.
"""

import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def capture(name: str, *args: str) -> None:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    if proc.returncode != 0 and name != "pr_checks":  # `gh pr checks` exits non-zero on red/pending checks
        raise SystemExit(f"gh {' '.join(args)} failed: {proc.stderr}")
    (FIXTURES / f"{name}.json").write_text(proc.stdout)


def main(repo: str, pr: str, issue: str) -> None:
    api = ["api", "-H", "Accept: application/vnd.github+json"]
    FIXTURES.mkdir(exist_ok=True)
    capture("repo_view", "repo", "view", repo, "--json", "name,owner")
    capture("api_repo", *api, "-X", "GET", f"repos/{repo}")
    capture("issue_view", "issue", "view", issue, "--repo", repo, "--json", "labels,title")
    capture("pr_view", "pr", "view", pr, "--repo", repo,
            "--json", "headRefName,headRefOid,labels,closingIssuesReferences,title")
    capture("pr_list", "pr", "list", "--repo", repo, "--state", "merged", "--limit", "3",
            "--json", "number,headRefName,closingIssuesReferences")
    capture("pr_checks", "pr", "checks", pr, "--repo", repo, "--json", "name,bucket,link")
    capture("pr_reviews", *api, "--paginate", "--slurp", f"repos/{repo}/pulls/{pr}/reviews")
    capture("labels", *api, "--paginate", "--slurp", f"repos/{repo}/labels?per_page=100")


if __name__ == "__main__":
    main(*sys.argv[1:])
