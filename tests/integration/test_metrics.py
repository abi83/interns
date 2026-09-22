"""Parsing one execution-log file into a pipeline-metrics record
(extract_metrics), and appending validated records to the orphan `metrics`
branch with retry-on-race (append_metrics). `git` is fully faked here, so
the append tests assert on the plumbing commands issued and the retry
count, not on real branch content.
"""

import json

import pytest

from testkit.harness import REPO, Scenario


@pytest.fixture
def scenario(tmp_path) -> Scenario:
    return Scenario(tmp_path)


# --- extract_metrics --------------------------------------------------------

def test_extract_metrics_builds_a_record_from_the_result_event(scenario):
    exec_file = scenario.dir / "execution.json"
    exec_file.write_text(json.dumps([
        {"type": "system"},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "push_branch"}]}},
        {"type": "assistant", "isSidechain": True,
         "message": {"content": [{"type": "tool_use", "name": "sub_agent_tool"}]}},
        {"type": "result", "session_id": "sess-1", "subtype": "success", "num_turns": 3,
         "duration_ms": 1000, "duration_api_ms": 800,
         "modelUsage": {"claude": {"inputTokens": 10, "outputTokens": 5, "costUSD": 0.01}}},
    ]))

    result = scenario.run("pipeline.entrypoint", "extract-metrics",
                          "--exec-file", str(exec_file), "--job", "coder", "--issue", "7", "--pr", "12")

    assert result.returncode == 0
    record = json.loads(result.stdout)
    assert record["job"] == "coder"
    assert record["issue"] == 7 and record["pr"] == 12
    assert record["session_id"] == "sess-1"
    assert record["tool_calls"] == {"push_branch": 1}  # the sub-agent call is excluded
    assert record["models"]["claude"]["input_tokens"] == 10


def test_extract_metrics_treats_missing_issue_and_pr_as_null(scenario):
    exec_file = scenario.dir / "execution.json"
    exec_file.write_text(json.dumps([{"type": "result", "session_id": "sess-1"}]))

    result = scenario.run("pipeline.entrypoint", "extract-metrics",
                          "--exec-file", str(exec_file), "--job", "estimator")

    assert result.returncode == 0
    record = json.loads(result.stdout)
    assert record["issue"] is None and record["pr"] is None


def test_extract_metrics_fails_when_the_execution_file_is_missing(scenario):
    result = scenario.run("pipeline.entrypoint", "extract-metrics",
                          "--exec-file", str(scenario.dir / "absent.json"), "--job", "coder")

    assert result.returncode == 1
    assert "execution file not found" in result.stderr


def test_extract_metrics_fails_when_there_is_no_result_event(scenario):
    exec_file = scenario.dir / "execution.json"
    exec_file.write_text(json.dumps([{"type": "system"}]))

    result = scenario.run("pipeline.entrypoint", "extract-metrics",
                          "--exec-file", str(exec_file), "--job", "coder")

    assert result.returncode == 1
    assert "no result event" in result.stderr


def test_extract_metrics_treats_a_truncated_file_the_same_as_no_result_event(scenario):
    exec_file = scenario.dir / "execution.json"
    exec_file.write_text('[{"type": "result", "session_id": "sess-1"')  # killed mid-write

    result = scenario.run("pipeline.entrypoint", "extract-metrics",
                          "--exec-file", str(exec_file), "--job", "coder")

    assert result.returncode == 1
    assert "no result event" in result.stderr


# --- append_metrics ----------------------------------------------------------

def _record(path, **fields):
    path.write_text(json.dumps(fields))


def test_append_metrics_fails_validation_before_touching_git(scenario):
    result = scenario.run("pipeline.entrypoint", "append-metrics", str(scenario.dir / "absent.json"),
                          env={"GH_TOKEN": "tok"})

    assert result.returncode == 1
    assert "no such file" in result.stderr
    assert scenario.calls("git") == []


def test_append_metrics_fails_validation_on_invalid_json(scenario):
    record = scenario.dir / "record.json"
    record.write_text("not json")

    result = scenario.run("pipeline.entrypoint", "append-metrics", str(record), env={"GH_TOKEN": "tok"})

    assert result.returncode == 1
    assert "not a JSON object" in result.stderr
    assert scenario.calls("git") == []


def test_append_metrics_fails_validation_on_a_valid_but_non_object_json_value(scenario):
    record = scenario.dir / "record.json"
    record.write_text("[1, 2, 3]")  # valid JSON, but not the single record object expected

    result = scenario.run("pipeline.entrypoint", "append-metrics", str(record), env={"GH_TOKEN": "tok"})

    assert result.returncode == 1
    assert "not a JSON object" in result.stderr
    assert scenario.calls("git") == []


def test_append_metrics_pushes_once_on_the_first_try(scenario):
    record = scenario.dir / "record.json"
    _record(record, job="coder", session_id="s1")
    for cmd in ("init", "config", "remote"):
        scenario.git(cmd)
    scenario.git("add")

    result = scenario.run("pipeline.entrypoint", "append-metrics", str(record), env={"GH_TOKEN": "tok"})

    assert result.returncode == 0
    assert "appended 1 record(s)" in result.stdout
    assert len(scenario.calls("git", "push")) == 1
    assert scenario.calls("git", "fetch") == [["fetch", "-q", "--depth=1", "origin", "metrics"]]


def test_append_metrics_requires_a_token(scenario):
    record = scenario.dir / "record.json"
    _record(record, job="coder")

    result = scenario.run("pipeline.entrypoint", "append-metrics", str(record), env={"GH_TOKEN": ""})

    assert result.returncode == 1
    assert "GH_TOKEN unset" in result.stderr
    assert scenario.calls("git") == []


def test_append_records_retries_on_a_losing_push_race(scenario, monkeypatch):
    from pipeline import append_metrics

    scenario.activate(monkeypatch)
    record = scenario.dir / "record.json"
    _record(record, job="coder", session_id="s1")
    for cmd in ("init", "config", "remote"):
        scenario.git(cmd)
    scenario.git("add")
    scenario.git("push", code=1)  # every push fails, forcing every retry

    sleeps: list[int] = []
    with pytest.raises(append_metrics.AppendMetricsError, match="failed after 3 attempts"):
        append_metrics.append_records([str(record)], remote="https://x@github.example/acme/widgets.git",
                                       run_id="4242", retries=3, sleep=sleeps.append)

    assert len(scenario.calls("git", "push")) == 3
    assert sleeps == [3, 6]  # backoff between attempts 1->2 and 2->3, none after the last


def test_append_metrics_main_reports_the_exhausted_retry_error(scenario, monkeypatch, capsys):
    """Same exhausted-retries path as test_append_records_retries_on_a_losing_push_race,
    but through `_main` -- proving the CLI surfaces the library's error message
    and exit code. Patches time.sleep instead of going through subprocess, so
    this doesn't block on real backoff delays."""
    from pipeline import append_metrics

    scenario.activate(monkeypatch)
    monkeypatch.setattr(append_metrics.time, "sleep", lambda _: None)
    from pipeline.ctx import ActionsCtx
    record = scenario.dir / "record.json"
    _record(record, job="coder", session_id="s1")
    for cmd in ("init", "config", "remote"):
        scenario.git(cmd)
    scenario.git("add")
    scenario.git("push", code=1)
    ctx = ActionsCtx(repo=REPO, token="tok", server_url="https://github.example", run_id="4242",
                     run_attempt=1, workspace=".", event_name="", reviewer_bot="", step_summary="")

    exit_code = append_metrics._main(ctx, [str(record)])

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "attempt 1/3 failed" in err and "attempt 2/3 failed" in err
    assert "push to metrics failed after 3 attempts" in err


def test_append_records_retries_on_a_failure_in_an_earlier_plumbing_step(scenario, monkeypatch):
    """The retry loop isn't push-specific: any step in one push attempt --
    here, `git add` -- failing forces the same clean-refetch-and-retry."""
    from pipeline import append_metrics

    scenario.activate(monkeypatch)
    record = scenario.dir / "record.json"
    _record(record, job="coder", session_id="s1")
    for cmd in ("init", "config", "remote"):
        scenario.git(cmd)
    scenario.git("add", code=1)  # every attempt fails here, before ever reaching commit/push

    sleeps: list[int] = []
    with pytest.raises(append_metrics.AppendMetricsError, match="failed after 2 attempts"):
        append_metrics.append_records([str(record)], remote="https://x@github.example/acme/widgets.git",
                                       run_id="4242", retries=2, sleep=sleeps.append)

    assert scenario.calls("git", "commit") == []
    assert scenario.calls("git", "push") == []
    assert sleeps == [3]


def test_append_records_is_a_noop_with_no_files(scenario, monkeypatch):
    from pipeline import append_metrics

    scenario.activate(monkeypatch)
    count = append_metrics.append_records([], remote="https://x@github.example/acme/widgets.git", run_id="4242")

    assert count == 0
    assert scenario.calls("git") == []


