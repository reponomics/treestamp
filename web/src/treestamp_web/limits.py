"""Per-client token buckets. State is per process and never persisted."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

_PRUNE_AT = 10_000


class RateLimiter:
    def __init__(self, per_minute: int, clock: Callable[[], float]) -> None:
        self._capacity = float(per_minute)
        self._rate = per_minute / 60.0
        self._clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}

    def acquire(self, identity: str) -> int | None:
        """Return ``None`` when allowed, otherwise whole seconds to wait."""
        if self._capacity <= 0:
            return None
        now = self._clock()
        tokens, last = self._buckets.get(identity, (self._capacity, now))
        tokens = min(self._capacity, tokens + (now - last) * self._rate)
        if tokens >= 1:
            self._buckets[identity] = (tokens - 1, now)
            self._prune(now)
            return None
        self._buckets[identity] = (tokens, now)
        return max(1, math.ceil((1 - tokens) / self._rate))

    def _prune(self, now: float) -> None:
        if len(self._buckets) < _PRUNE_AT:
            return
        stale = [
            identity
            for identity, (tokens, last) in self._buckets.items()
            if tokens + (now - last) * self._rate >= self._capacity
        ]
        for identity in stale:
            del self._buckets[identity]
