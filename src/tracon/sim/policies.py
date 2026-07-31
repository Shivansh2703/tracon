"""Scheduling policies: given the ready queue, choose the next batch.

The baseline is FIFO — take the k oldest-ready requests, exactly what a
dynamic-batching front end does. Every other policy implements the same protocol
and reorders the queue instead. Each policy exists twice: a Python prototype
(the golden behavior) and its compiled port in ``tracon_core``; parity between
the two is a standing test, and ties always resolve to queue order so identical
inputs give identical selections everywhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import tracon_core

if TYPE_CHECKING:
    from tracon.sim.server import Request
    from tracon.sim.workload import StreamKey

# SJF guard: a request waiting this long jumps the line. A backstop, not the rule —
# set above the baseline's p95 queue wait (11.9s at native load, 1 executor) so it
# trips on pathological waits only; a tight guard collapses SJF back into FIFO.
STARVE_MS = 60_000.0


class Policy(Protocol):
    name: str

    def select(self, queue: list[Request], k: int, now: float) -> list[Request]:
        """Pick up to k requests from the ready queue (queue is ready-order)."""
        ...


class FIFOPolicy:
    name = "fifo"

    def select(self, queue: list[Request], k: int, now: float) -> list[Request]:
        return queue[:k]


class SJFPolicy:
    """Oracle shortest-job-first with a starvation guard.

    Oracle: ``service_ms`` is the traced value a real server could only estimate.
    Requests waiting >= starve_ms jump the line oldest-first; the rest order by
    service time. All sorts are stable — ties keep queue (ready) order.
    """

    name = "sjf"

    def __init__(self, starve_ms: float = STARVE_MS) -> None:
        self.starve_ms = starve_ms

    def select(self, queue: list[Request], k: int, now: float) -> list[Request]:
        starved = [r for r in queue if now - r.ready_ms >= self.starve_ms]
        starved.sort(key=lambda r: r.ready_ms)
        fresh = [r for r in queue if now - r.ready_ms < self.starve_ms]
        fresh.sort(key=lambda r: r.service_ms)
        return (starved + fresh)[:k]


class UnblockPolicy:
    """Dependency-aware: serve the request whose completion unblocks the most
    waiting work.

    ``waiters`` counts chains provably blocked on this request's chain: a
    same-stream next turn whose arrival already fired (the queued-prompt case —
    74% of real prompts arrive while the agent is busy), or a parent gated on a
    sync spawn. Direct counts only, no transitive closure. Zero-waiter requests
    and ties fall back to queue order; the starvation guard matches SJF's.
    """

    name = "unblock"

    def __init__(self, starve_ms: float = STARVE_MS) -> None:
        self.starve_ms = starve_ms

    def select(self, queue: list[Request], k: int, now: float) -> list[Request]:
        starved = [r for r in queue if now - r.ready_ms >= self.starve_ms]
        starved.sort(key=lambda r: r.ready_ms)
        fresh = [r for r in queue if now - r.ready_ms < self.starve_ms]
        fresh.sort(key=lambda r: -r.waiters())
        return (starved + fresh)[:k]


class CorePolicy:
    """Adapter over the compiled core: plain views cross, positions come back.

    The adapter never reorders, filters, or decides — selection logic lives only
    in C++, otherwise parity with the Python prototypes proves nothing.
    """

    def __init__(self, kernel: str, starve_ms: float = STARVE_MS) -> None:
        self.name = f"core-{kernel}"
        self._kernel = kernel
        self._starve_ms = starve_ms
        self._streams: dict[StreamKey, int] = {}

    def _views(self, queue: list[Request]) -> list[tracon_core.RequestView]:
        return [
            tracon_core.RequestView(
                req=i,
                stream=self._streams.setdefault(r.stream, len(self._streams)),
                ready_ms=r.ready_ms,
                service_ms=r.service_ms,
                waiters=r.waiters(),
            )
            for i, r in enumerate(queue)
        ]

    def select(self, queue: list[Request], k: int, now: float) -> list[Request]:
        views = self._views(queue)
        if self._kernel == "fifo":
            picked = tracon_core.select_fifo_views(views, k)
        elif self._kernel == "sjf":
            picked = tracon_core.select_sjf(views, k, now, self._starve_ms)
        elif self._kernel == "unblock":
            picked = tracon_core.select_unblock(views, k, now, self._starve_ms)
        else:
            raise ValueError(f"unknown core kernel: {self._kernel}")
        return [queue[i] for i in picked]


def make_policy(name: str) -> Policy:
    if name == "fifo":
        return FIFOPolicy()
    if name == "sjf":
        return SJFPolicy()
    if name == "unblock":
        return UnblockPolicy()
    if name.startswith("core-"):
        return CorePolicy(name.removeprefix("core-"))
    raise ValueError(f"unknown policy: {name}")
