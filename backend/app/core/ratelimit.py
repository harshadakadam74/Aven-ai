"""Small in-memory sliding-window rate limiter for sensitive endpoints."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable


class RateLimiter:
    def __init__(
        self,
        max_calls: int,
        period_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_calls < 1 or period_seconds <= 0:
            raise ValueError("max_calls and period_seconds must be positive")
        self._max = max_calls
        self._period = period_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self._period:
                hits.popleft()
            if len(hits) >= self._max:
                return False
            hits.append(now)
            return True
