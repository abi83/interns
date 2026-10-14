import json
import subprocess
import unittest
from unittest.mock import patch

from interns import gh
from interns.domain import actor_guard
from interns.domain.actor_guard import Actor
from testkit import events

USER = Actor("alice", "User")


def gh_says(*bodies: object):
    procs = [subprocess.CompletedProcess(args=["gh"], returncode=0, stdout=json.dumps(b), stderr="") for b in bodies]
    return patch("interns.gh.transport.subprocess.run", side_effect=procs)


def refusal(actor: Actor, permission: str = "write") -> str:
    with gh_says({"permission": permission}):
        return actor_guard.refusal("acme/widgets", (actor,))


class EventActorsTests(unittest.TestCase):
    def test_label_pull_request_and_dispatch_have_the_sender_as_only_actor(self):
        payloads = {
            "issues": events.issues_labeled(7, "status:ready", sender="alice"),
            "pull_request": events.pull_request(sender="alice"),
            "workflow_dispatch": events.dispatch(sender="alice", phase="coder"),
        }
        for name, payload in payloads.items():
            with self.subTest(name=name):
                self.assertEqual(actor_guard.event_actors(name, payload), (USER,))

    def test_workflow_run_adds_the_upstream_actors_once_each(self):
        payload = events.workflow_run(sender="alice", run_actor="bob", triggering_actor="alice")
        self.assertEqual(actor_guard.event_actors("workflow_run", payload), (USER, Actor("bob", "User")))

    def test_payload_without_sender_raises(self):
        with self.assertRaises(KeyError):
            actor_guard.event_actors("issues", {})


class RefusalTests(unittest.TestCase):
    def test_user_with_write_or_admin_is_accepted(self):
        for level in ("write", "admin"):
            with self.subTest(level=level):
                self.assertEqual(refusal(USER, level), "")

    def test_user_without_write_is_refused_with_the_level(self):
        for level in ("read", "none"):
            with self.subTest(level=level):
                self.assertIn(f"'{level}'", refusal(USER, level))

    def test_pipeline_bots_are_accepted_without_a_lookup(self):
        for login in ("github-actions[bot]", "interns-coder[bot]", "interns-reviewer-acme[bot]", "interns-triage-acme[bot]"):
            with self.subTest(login=login), patch("interns.gh.transport.subprocess.run", side_effect=AssertionError("looked up")):
                self.assertEqual(actor_guard.refusal("acme/widgets", (Actor(login, "Bot"),)), "")

    def test_other_bots_and_account_types_are_refused(self):
        for actor in (Actor("dependabot[bot]", "Bot"), Actor("interns-evil[bot]", "Bot"), Actor("acme", "Organization")):
            with self.subTest(actor=actor):
                self.assertTrue(refusal(actor).startswith("actor refused"))

    def test_every_actor_must_pass(self):
        with gh_says({"permission": "write"}, {"permission": "read"}):
            reason = actor_guard.refusal("acme/widgets", (USER, Actor("bob", "User")))
        self.assertIn("bob", reason)

    def test_unresolvable_permission_raises(self):
        for response in (None, {}, {"permission": 3}):
            with self.subTest(response=response), gh_says(response), self.assertRaises(gh.GhError):
                actor_guard.refusal("acme/widgets", (USER,))

    def test_failed_lookup_raises(self):
        failure = subprocess.CalledProcessError(1, ["gh"], stderr="HTTP 404")
        with (
            patch("interns.gh.transport.subprocess.run", side_effect=failure),
            self.assertRaisesRegex(gh.GhError, "cannot resolve alice's permission"),
        ):
            actor_guard.refusal("acme/widgets", (USER,))
