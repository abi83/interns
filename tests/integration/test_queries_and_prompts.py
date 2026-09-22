"""Read-only workflow-YAML helpers: `gh_query`'s per-value lookups and
`prompt`'s file-concatenation, plus `resolve_issue_template`'s skeleton
build. None of these touch labels or comments, so each test asserts on
stdout / $GITHUB_OUTPUT directly instead.
"""

import pytest

from testkit.harness import REPO, Scenario

PR = "12"
ISSUE = "7"


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


def test_head_ref_prints_the_branch_name(scenario):
    scenario.gh("pr", "view", "headRefName", stdout={"headRefName": "issue-7-fix"})

    result = scenario.run("pipeline.gh_query", REPO, "head-ref", PR)

    assert result.returncode == 0
    assert result.stdout.strip() == "issue-7-fix"


def test_head_sha_prints_the_commit(scenario):
    scenario.gh("pr", "view", "headRefOid", stdout={"headRefOid": "deadbeef"})

    result = scenario.run("pipeline.gh_query", REPO, "head-sha", PR)

    assert result.returncode == 0
    assert result.stdout.strip() == "deadbeef"


def test_closing_issue_prints_the_first_linked_number(scenario):
    scenario.gh("pr", "view", "closingIssuesReferences",
                stdout={"closingIssuesReferences": [{"number": 7}, {"number": 9}]})

    result = scenario.run("pipeline.gh_query", REPO, "closing-issue", PR)

    assert result.returncode == 0
    assert result.stdout.strip() == "7"


def test_closing_issue_is_empty_when_the_pr_closes_nothing(scenario):
    scenario.gh("pr", "view", "closingIssuesReferences", stdout={"closingIssuesReferences": []})

    result = scenario.run("pipeline.gh_query", REPO, "closing-issue", PR)

    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_pr_for_issue_finds_the_open_pr_that_closes_it(scenario):
    scenario.gh("pr", "list", stdout=[
        {"number": 3, "headRefName": "issue-3", "closingIssuesReferences": [{"number": 3}]},
        {"number": int(PR), "headRefName": "issue-7-fix", "closingIssuesReferences": [{"number": int(ISSUE)}]},
    ])

    result = scenario.run("pipeline.gh_query", REPO, "pr-for-issue", ISSUE)

    assert result.returncode == 0
    assert result.stdout.splitlines() == [f"pr_number={PR}", "head_ref=issue-7-fix"]


def test_pr_for_issue_is_empty_when_no_open_pr_closes_it(scenario):
    scenario.gh("pr", "list", stdout=[
        {"number": 3, "headRefName": "issue-3", "closingIssuesReferences": [{"number": 99}]},
    ])

    result = scenario.run("pipeline.gh_query", REPO, "pr-for-issue", ISSUE)

    assert result.returncode == 0
    assert result.stdout.splitlines() == ["pr_number=", "head_ref="]


def test_prompt_concatenates_files_into_one_output(scenario):
    first = scenario.workspace / "a.md"
    second = scenario.workspace / "b.md"
    first.write_text("Part one.\n")
    second.write_text("Part two.\n")

    result = scenario.run("pipeline.prompt", str(first), str(second))

    assert result.returncode == 0
    assert result.outputs["text"] == "Part one.\nPart two."


def test_resolve_issue_template_uses_the_builtin_skeleton(scenario):
    builtin_dir = scenario.dir / "builtin"
    builtin_dir.mkdir()
    (builtin_dir / "bug.md").write_text("---\nname: Bug\n---\n\n## Description\n\nbody\n\n## Impact\n\nbody\n")

    result = scenario.run("pipeline.resolve_issue_template", "--builtin-dir", str(builtin_dir),
                          "--consumer-dir", str(scenario.workspace / "absent"), "--types", "bug")

    assert result.returncode == 0
    assert result.outputs["skeleton"] == "type:bug\n## Description\n## Impact"


def test_resolve_issue_template_prefers_a_consumer_override(scenario):
    builtin_dir = scenario.dir / "builtin"
    consumer_dir = scenario.dir / "consumer"
    builtin_dir.mkdir()
    consumer_dir.mkdir()
    (builtin_dir / "bug.md").write_text("## Builtin Only\n")
    (consumer_dir / "bug.md").write_text("## Consumer Heading\n")

    result = scenario.run("pipeline.resolve_issue_template", "--builtin-dir", str(builtin_dir),
                          "--consumer-dir", str(consumer_dir), "--types", "bug")

    assert result.returncode == 0
    assert "## Consumer Heading" in result.outputs["skeleton"]
    assert "## Builtin Only" not in result.outputs["skeleton"]


def test_resolve_issue_template_fails_for_an_unknown_type(scenario):
    builtin_dir = scenario.dir / "builtin"
    builtin_dir.mkdir()

    result = scenario.run("pipeline.resolve_issue_template", "--builtin-dir", str(builtin_dir),
                          "--consumer-dir", str(scenario.workspace / "absent"), "--types", "bug")

    assert result.returncode != 0
    assert "no template for 'bug'" in result.stderr
