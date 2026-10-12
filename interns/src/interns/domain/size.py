"""Rolls the estimator's four Low|Mid|High scores up into a size."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Keyed by (#High, #Mid) across the four scores: size grows with either
# count, and 3+ highs is always XL.
_ROLL_UP_TABLE: dict[tuple[int, int], str] = {
    (0, 0): "XS", (0, 1): "S",  (0, 2): "S",  (0, 3): "M",  (0, 4): "M",
    (1, 0): "M",  (1, 1): "M",  (1, 2): "M",  (1, 3): "L",
    (2, 0): "L",  (2, 1): "L",  (2, 2): "L",
    (3, 0): "XL", (3, 1): "XL",
    (4, 0): "XL",
}


def roll_up_size(blast: str, touch: str, human: str, review: str) -> str:
    """Map four Low|Mid|High scores to XS|S|M|L|XL via the (#High, #Mid) key."""
    highs = mids = 0
    for score in (blast, touch, human, review):
        s = score.strip().lower()
        if s == "high":
            highs += 1
        elif s == "mid":
            mids += 1
        elif s != "low":
            raise ValueError(f"Not a Low|Mid|High score: {score!r}")
    return _ROLL_UP_TABLE[(highs, mids)]


@dataclass(frozen=True)
class Score:
    level: Literal["Low", "Mid", "High"]
    reason: str


@dataclass(frozen=True)
class Estimation:
    """The estimator's four scored dimensions; every one is required."""

    blast_radius: Score
    touch: Score
    human_involvement: Score
    review_overhead: Score

    def size(self) -> str:
        return roll_up_size(
            self.blast_radius.level, self.touch.level, self.human_involvement.level, self.review_overhead.level
        )

    def comment(self) -> str:
        return "\n".join((
            f"BLAST RADIUS: {self.blast_radius.level} — {self.blast_radius.reason}",
            f"TOUCH: {self.touch.level} — {self.touch.reason}",
            f"HUMAN INVOLVEMENT: {self.human_involvement.level} — {self.human_involvement.reason}",
            f"REVIEW OVERHEAD: {self.review_overhead.level} — {self.review_overhead.reason}",
        ))
