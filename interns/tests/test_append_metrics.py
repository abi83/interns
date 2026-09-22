import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from interns import append_metrics
from interns.ctx import ActionsCtx


def _git(args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _make_bare_repo(tmp: Path) -> Path:
    bare = tmp / "origin.git"
    _git(["init", "-q", "--bare", str(bare)], tmp)
    return bare


def _seed_metrics_branch(bare: Path, tmp: Path, lines: list[str]) -> None:
    """Pushes (or re-pushes, fast-forward) the `metrics` branch with `lines`
    already in metrics.jsonl -- used both to pre-seed a branch and, in the
    retry test, to land a competing commit mid-race."""
    work = tempfile.mkdtemp(dir=tmp)
    _git(["clone", "-q", str(bare), work], tmp)
    _git(["config", "user.email", "seed@example.com"], work)
    _git(["config", "user.name", "seed"], work)
    fetched = subprocess.run(["git", "fetch", "-q", "origin", "metrics"],
                              cwd=work, capture_output=True, text=True)
    if fetched.returncode == 0:
        _git(["checkout", "-q", "-b", "metrics", "FETCH_HEAD"], work)
    else:
        _git(["checkout", "-q", "--orphan", "metrics"], work)
    (Path(work) / "metrics.jsonl").write_text("".join(l + "\n" for l in lines))
    _git(["add", "metrics.jsonl"], work)
    _git(["commit", "-q", "-m", "seed"], work)
    _git(["push", "-q", "origin", "HEAD:metrics"], work)


def _branch_content(bare: Path, tmp: Path) -> str:
    work = tempfile.mkdtemp(dir=tmp)
    _git(["clone", "-q", "--branch", "metrics", str(bare), work], tmp)
    return (Path(work) / "metrics.jsonl").read_text()


def _record_file(tmp: Path, obj: dict) -> Path:
    path = Path(tempfile.mkstemp(dir=tmp, suffix=".json")[1])
    path.write_text(json.dumps(obj))
    return path


class ReadRecordsValidationTests(unittest.TestCase):
    def test_rejects_a_file_that_is_not_a_json_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("not json")
            with self.assertRaises(append_metrics.AppendMetricsError):
                append_metrics.append_records([str(bad)], remote="unused", run_id="1")

    def test_rejects_a_json_array_as_not_an_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            arr = Path(tmp) / "arr.json"
            arr.write_text("[1, 2, 3]")
            with self.assertRaises(append_metrics.AppendMetricsError):
                append_metrics.append_records([str(arr)], remote="unused", run_id="1")

    def test_rejects_a_missing_file(self):
        with self.assertRaises(append_metrics.AppendMetricsError):
            append_metrics.append_records(["/no/such/record.json"], remote="unused", run_id="1")


class AppendRecordsTests(unittest.TestCase):
    def test_creates_the_branch_on_first_use_and_commits_records(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            bare = _make_bare_repo(tmp)
            record = _record_file(tmp, {"schema_version": 1, "job": "coder"})

            count = append_metrics.append_records([str(record)], remote=str(bare), run_id="42")

            self.assertEqual(count, 1)
            content = _branch_content(bare, tmp)
            self.assertEqual(json.loads(content.strip()), {"schema_version": 1, "job": "coder"})

    def test_appends_onto_an_existing_branch_without_clobbering_it(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            bare = _make_bare_repo(tmp)
            _seed_metrics_branch(bare, tmp, ['{"job":"existing"}'])
            record = _record_file(tmp, {"job": "new"})

            count = append_metrics.append_records([str(record)], remote=str(bare), run_id="7")

            self.assertEqual(count, 1)
            lines = _branch_content(bare, tmp).splitlines()
            self.assertEqual(lines, ['{"job":"existing"}', '{"job":"new"}'])

    def test_no_records_is_a_no_op(self):
        count = append_metrics.append_records([], remote="unused", run_id="1")
        self.assertEqual(count, 0)


class RetryPathTests(unittest.TestCase):
    def test_one_failed_push_then_a_success(self):
        """Simulates the exact race append-metrics exists to survive: a
        second writer lands a commit on `metrics` between our fetch and our
        push, our push is rejected as non-fast-forward, and the retry
        re-fetches (now including the competing commit) and succeeds."""
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            bare = _make_bare_repo(tmp)
            _seed_metrics_branch(bare, tmp, ["existing"])
            record = _record_file(tmp, {"job": "coder"})

            real_run_git = append_metrics._run_git
            state = {"raced": False}

            def racing_run_git(args, cwd):
                if args[:1] == ["push"] and not state["raced"]:
                    state["raced"] = True
                    _seed_metrics_branch(bare, tmp, ["existing", "competitor"])
                return real_run_git(args, cwd)

            sleeps = []
            with patch.object(append_metrics, "_run_git", side_effect=racing_run_git):
                count = append_metrics.append_records(
                    [str(record)], remote=str(bare), run_id="42", sleep=sleeps.append,
                )

            self.assertEqual(count, 1)
            self.assertEqual(sleeps, [3])
            lines = _branch_content(bare, tmp).splitlines()
            self.assertEqual(lines[:2], ["existing", "competitor"])
            self.assertEqual(json.loads(lines[2]), {"job": "coder"})

    def test_exhausting_all_retries_raises(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            record = _record_file(tmp, {"job": "coder"})
            sleeps = []
            with patch.object(append_metrics, "_run_git", return_value=subprocess.CompletedProcess([], 1)):
                with self.assertRaises(append_metrics.AppendMetricsError):
                    append_metrics.append_records(
                        [str(record)], remote="/no/such/remote", run_id="1",
                        retries=3, sleep=sleeps.append,
                    )
            self.assertEqual(sleeps, [3, 6])


class CliTests(unittest.TestCase):
    def _ctx(self, token="tok123", repo="owner/repo", server_url="https://github.com", run_id="42"):
        return ActionsCtx(repo=repo, token=token, server_url=server_url, run_id=run_id,
                          run_attempt=1, workspace=".", event_name="", reviewer_bot="", step_summary="")

    def test_errors_with_no_arguments(self):
        with self.assertRaises(SystemExit):
            append_metrics._main(self._ctx(), [])

    def test_builds_remote_from_ctx_and_reports_success(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            record = _record_file(tmp, {"job": "coder"})
            with patch.object(append_metrics, "append_records", return_value=1) as mock_append, \
                 patch("builtins.print") as mock_print:
                status = append_metrics._main(self._ctx(), [str(record)])

        self.assertEqual(status, 0)
        _, kwargs = mock_append.call_args
        self.assertEqual(kwargs["remote"], "https://x-access-token:tok123@github.com/owner/repo.git")
        self.assertEqual(kwargs["run_id"], "42")
        mock_print.assert_called_once()

    def test_reports_failure_after_exhausted_retries(self):
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            record = _record_file(tmp, {"job": "coder"})
            with patch.object(append_metrics, "append_records",
                               side_effect=append_metrics.AppendMetricsError("push to metrics failed after 3 attempts")):
                status = append_metrics._main(self._ctx(), [str(record)])

        self.assertEqual(status, 1)


if __name__ == "__main__":
    unittest.main()
