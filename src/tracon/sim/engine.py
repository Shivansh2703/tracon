"""Minimal deterministic discrete-event engine: a time-ordered callback heap."""

from __future__ import annotations

import heapq
from collections.abc import Callable


class Engine:
    def __init__(self) -> None:
        self.now = 0.0
        self._heap: list[tuple[float, int, Callable[[], None]]] = []
        self._seq = 0  # FIFO tie-break keeps same-time events deterministic

    def at(self, time_ms: float, fn: Callable[[], None]) -> None:
        heapq.heappush(self._heap, (max(time_ms, self.now), self._seq, fn))
        self._seq += 1

    def after(self, delay_ms: float, fn: Callable[[], None]) -> None:
        self.at(self.now + delay_ms, fn)

    def run(self) -> None:
        while self._heap:
            now, _, fn = heapq.heappop(self._heap)
            self.now = now
            fn()
