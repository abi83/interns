"""Rolls the estimator's four Low|Mid|High scores up into a size."""

from __future__ import annotations

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
