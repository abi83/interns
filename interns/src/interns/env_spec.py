"""What env a command needs from its workflow step, declared next to the command.

`always` holds the variables read on every path; `by_phase` the ones read only
when `phases(argv)` names that phase (e.g. the reviewer bot, needed by the
review phase alone). `tests/guards/test_step_env.py` checks the workflows
against these declarations and the code against both."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field


def _no_phases(argv: list[str]) -> Collection[str]:
    return ()


@dataclass(frozen=True)
class EnvSpec:
    always: frozenset[str] = frozenset()
    by_phase: Mapping[str, frozenset[str]] = field(default_factory=dict)
    phases: Callable[[list[str]], Collection[str]] = _no_phases

    @classmethod
    def of(cls, *names: str) -> EnvSpec:
        return cls(always=frozenset(names))

    def required(self, argv: list[str]) -> frozenset[str]:
        phase_env = (self.by_phase.get(phase, frozenset()) for phase in self.phases(argv))
        return self.always.union(*phase_env)

    def every_path(self) -> frozenset[str]:
        return self.always.union(*self.by_phase.values())
