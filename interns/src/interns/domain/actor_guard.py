"""Who may start a pipeline job.

Every actor behind an event must be a user with write access to the repo or one
of the pipeline's own identities. For `workflow_run` that includes the upstream
run's actors, because the run itself is not trusted input. An actor that cannot
be resolved raises, so the job never starts on a guess.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import gh

PIPELINE_BOT = re.compile(r"github-actions\[bot\]|interns-(coder|reviewer|triage)(-[a-z0-9-]+)?\[bot\]")
WRITE_PERMISSIONS = frozenset({"admin", "write"})


@dataclass(frozen=True)
class Actor:
    login: str
    type: str


def _actor(node: dict) -> Actor:
    return Actor(login=node["login"], type=node["type"])


def event_actors(name: str, payload: dict) -> tuple[Actor, ...]:
    sender = _actor(payload["sender"])
    if name != "workflow_run":
        return (sender,)
    run = payload["workflow_run"]
    return tuple(dict.fromkeys((sender, _actor(run["actor"]), _actor(run["triggering_actor"]))))


def _refusal(repo: str, actor: Actor) -> str:
    if actor.type == "Bot":
        return "" if PIPELINE_BOT.fullmatch(actor.login) else f"{actor.login} is a bot that is not a pipeline identity"
    if actor.type != "User":
        return f"{actor.login} is a {actor.type}, not a user or a pipeline identity"
    permission = gh.collaborator_permission(repo, actor.login)
    if permission in WRITE_PERMISSIONS:
        return ""
    return f"{actor.login} has {permission!r} access to {repo}; write is required"


def refusal(repo: str, actors: tuple[Actor, ...]) -> str:
    """Why the event's actors may not start a job; empty when all may."""
    for actor in actors:
        reason = _refusal(repo, actor)
        if reason:
            return f"actor refused: {reason}"
    return ""
