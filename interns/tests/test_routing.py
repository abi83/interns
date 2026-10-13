import unittest

from interns.domain.routing import (
    Dispatch,
    IssueLabeled,
    Job,
    PullRequestEvent,
    Route,
    RouteConfig,
    parse_event,
    route,
)
from testkit import events

BOTH = RouteConfig(handles=frozenset(Job) - {Job.NONE})
ISSUE_WORKFLOW = RouteConfig(handles=frozenset({Job.REFINE, Job.ESTIMATE}))
CODE_WORKFLOW = RouteConfig(handles=frozenset({Job.CODER, Job.REVIEWER, Job.PR_CLOSED}))


def pr_event(action="opened", *, draft=False, fork=False) -> PullRequestEvent:
    return PullRequestEvent(action=action, number=12, draft=draft, fork=fork, author_login="alice", author_type="User")


class RouteLabelTests(unittest.TestCase):
    def test_each_status_label_starts_its_job(self):
        cases = {
            "status:needs-refinement": Job.REFINE,
            "status:refined": Job.ESTIMATE,
            "status:ready": Job.CODER,
        }
        for label, job in cases.items():
            with self.subTest(label=label):
                self.assertEqual(route(IssueLabeled(7, label), BOTH), Route(job, issue=7))

    def test_other_labels_start_nothing(self):
        for label in ("status:in-progress", "type:bug", "priority:high"):
            with self.subTest(label=label):
                routed = route(IssueLabeled(7, label), BOTH)
                self.assertEqual(routed.job, Job.NONE)
                self.assertIn(label, routed.skip_reason)


class RoutePullRequestTests(unittest.TestCase):
    def test_open_ready_and_pushed_prs_start_the_reviewer(self):
        for action in ("opened", "ready_for_review", "synchronize"):
            with self.subTest(action=action):
                self.assertEqual(route(pr_event(action), BOTH), Route(Job.REVIEWER, pr=12))

    def test_closing_starts_pr_closed_even_for_drafts_and_forks(self):
        for draft, fork in ((False, False), (True, False), (False, True)):
            with self.subTest(draft=draft, fork=fork):
                self.assertEqual(route(pr_event("closed", draft=draft, fork=fork), BOTH), Route(Job.PR_CLOSED, pr=12))

    def test_draft_prs_are_not_reviewed(self):
        routed = route(pr_event(draft=True), BOTH)
        self.assertEqual((routed.job, routed.pr), (Job.NONE, 12))
        self.assertIn("draft", routed.skip_reason)

    def test_fork_prs_are_not_reviewed(self):
        routed = route(pr_event(fork=True), BOTH)
        self.assertEqual(routed.job, Job.NONE)
        self.assertIn("fork", routed.skip_reason)


class RouteDispatchTests(unittest.TestCase):
    def test_each_phase_starts_its_job_with_its_operand(self):
        cases = [
            (Dispatch("refine", 7, None, False), Route(Job.REFINE, issue=7)),
            (Dispatch("estimate", 7, None, False), Route(Job.ESTIMATE, issue=7)),
            (Dispatch("coder", 7, None, False), Route(Job.CODER, issue=7)),
            (Dispatch("reviewer", None, 12, False), Route(Job.REVIEWER, pr=12)),
        ]
        for event, expected in cases:
            with self.subTest(phase=event.phase):
                self.assertEqual(route(event, BOTH), expected)

    def test_a_coder_dispatch_can_be_a_fix_round(self):
        self.assertEqual(route(Dispatch("coder", 7, None, True), BOTH), Route(Job.CODER, issue=7, fix_round=True))

    def test_fix_round_is_ignored_outside_the_coder_phase(self):
        self.assertFalse(route(Dispatch("refine", 7, None, True), BOTH).fix_round)

    def test_a_phase_without_its_operand_raises(self):
        for event in (Dispatch("coder", None, 12, False), Dispatch("reviewer", 7, None, False)):
            with self.subTest(phase=event.phase), self.assertRaises(ValueError):
                route(event, BOTH)

    def test_an_unknown_phase_raises(self):
        for phase in ("", "deploy"):
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                route(Dispatch(phase, 7, 12, False), BOTH)


class WorkflowOwnershipTests(unittest.TestCase):
    def test_each_workflow_only_runs_its_own_jobs(self):
        cases = [
            (IssueLabeled(7, "status:ready"), ISSUE_WORKFLOW, Job.NONE),
            (IssueLabeled(7, "status:ready"), CODE_WORKFLOW, Job.CODER),
            (IssueLabeled(7, "status:refined"), CODE_WORKFLOW, Job.NONE),
            (IssueLabeled(7, "status:refined"), ISSUE_WORKFLOW, Job.ESTIMATE),
            (Dispatch("reviewer", None, 12, False), ISSUE_WORKFLOW, Job.NONE),
            (pr_event("closed"), ISSUE_WORKFLOW, Job.NONE),
        ]
        for event, config, job in cases:
            with self.subTest(event=event, handles=sorted(config.handles)):
                self.assertEqual(route(event, config).job, job)

    def test_a_job_of_the_other_workflow_says_so(self):
        self.assertIn("other workflow", route(IssueLabeled(7, "status:ready"), ISSUE_WORKFLOW).skip_reason)

    def test_handles_parses_a_comma_separated_list(self):
        self.assertEqual(RouteConfig.parse("refine,estimate").handles, frozenset({Job.REFINE, Job.ESTIMATE}))

    def test_an_unknown_job_name_raises(self):
        with self.assertRaises(ValueError):
            RouteConfig.parse("refine,deploy")


class ParseEventTests(unittest.TestCase):
    def test_issues_labeled(self):
        self.assertEqual(parse_event("issues", events.issues_labeled(7, "status:ready")), IssueLabeled(7, "status:ready"))

    def test_pull_request(self):
        parsed = parse_event("pull_request", events.pull_request("synchronize", 12, draft=True, login="bot[bot]", user_type="Bot"))
        self.assertEqual(parsed, PullRequestEvent("synchronize", 12, True, False, "bot[bot]", "Bot"))

    def test_a_deleted_head_repo_counts_as_a_fork(self):
        payload = events.pull_request()
        payload["pull_request"]["head"]["repo"] = None
        parsed = parse_event("pull_request", payload)
        assert isinstance(parsed, PullRequestEvent)
        self.assertTrue(parsed.fork)

    def test_dispatch_inputs(self):
        parsed = parse_event("workflow_dispatch", events.dispatch(phase="coder", issue_number="7", fix_round="true"))
        self.assertEqual(parsed, Dispatch("coder", 7, None, True))

    def test_dispatch_without_inputs(self):
        self.assertEqual(parse_event("workflow_dispatch", {"inputs": None}), Dispatch("", None, None, False))

    def test_dispatch_accepts_boolean_fix_round(self):
        parsed = parse_event("workflow_dispatch", {"inputs": {"phase": "coder", "issue_number": "7", "fix_round": True}})
        assert isinstance(parsed, Dispatch)
        self.assertTrue(parsed.fix_round)

    def test_unsupported_events_and_actions_raise(self):
        cases = [
            ("push", {}),
            ("issues", {"action": "opened", "issue": {"number": 7}}),
            ("pull_request", {**events.pull_request(), "action": "labeled"}),
            ("pull_request", {}),
        ]
        for name, payload in cases:
            with self.subTest(name=name, action=payload.get("action")), self.assertRaises((ValueError, KeyError)):
                parse_event(name, payload)


if __name__ == "__main__":
    unittest.main()
