"""Single mechanism for best-effort operations.

Any operation that may fail for transient external reasons (rate limits,
missing permissions) where the pipeline should continue without its result
must go through `call`. No other code swallows exceptions.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def call(reason: str, exc_type: type[BaseException], fn: Callable[..., T], /, *args, **kwargs) -> T | None:
    """Run fn(*args, **kwargs) as best-effort.

    Returns the real value, or None with a warning when fn raises exc_type.
    Any other exception propagates. The reason string is required and must
    name why this specific failure is non-fatal.
    """
    if not reason:
        raise ValueError("best_effort.call: reason must not be empty")
    try:
        return fn(*args, **kwargs)
    except exc_type as exc:
        print(f"warning: {getattr(fn, '__name__', repr(fn))} unavailable ({reason}): {exc}", file=sys.stderr)
        return None
