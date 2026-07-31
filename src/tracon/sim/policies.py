"""Scheduling policies: given the ready queue, choose the next batch.

The baseline is FIFO — take the k oldest-ready requests, exactly what a
dynamic-batching front end does. Every other policy implements the same protocol
and reorders the queue instead. Each policy exists twice: a Python prototype
(the golden behavior) and its compiled port in ``tracon_core``; parity between
the two is a standing test, and ties always resolve to queue order so identical
inputs give identical selections everywhere.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Protocol

import grpc
import tracon_core

from tracon.schedpb import scheduler_pb2, scheduler_pb2_grpc

if TYPE_CHECKING:
    from tracon.sim.server import ModelServer, Request
    from tracon.sim.workload import StreamKey

GRPC_ADDR_ENV = "TRACON_GRPC_ADDR"
GRPC_ADDR_DEFAULT = "127.0.0.1:50351"

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


class AffinityPolicy:
    """Session-aware: requests whose stream context is warm on a free executor go
    first, avoiding cold-context reload penalties; FIFO within warm/cold groups.
    The server reports residency via ``bind_server`` (98.9% of real model input is
    cache-read — context locality is the dominant regime)."""

    name = "affinity"

    def __init__(self, starve_ms: float = STARVE_MS) -> None:
        self.starve_ms = starve_ms
        self._server: ModelServer | None = None

    def bind_server(self, server: ModelServer) -> None:
        self._server = server

    def select(self, queue: list[Request], k: int, now: float) -> list[Request]:
        warm = self._server.warm_free_streams() if self._server is not None else set()
        starved = [r for r in queue if now - r.ready_ms >= self.starve_ms]
        starved.sort(key=lambda r: r.ready_ms)
        fresh = [r for r in queue if now - r.ready_ms < self.starve_ms]
        fresh.sort(key=lambda r: 0 if r.stream in warm else 1)
        return (starved + fresh)[:k]


class TraconPolicy:
    """The flagship: dependency-aware first (most blocked waiters), session-aware
    second (warm context), FIFO last. Never reads ``service_ms`` — unlike oracle
    SJF, a real server could run this policy as-is."""

    name = "tracon"

    def __init__(self, starve_ms: float = STARVE_MS) -> None:
        self.starve_ms = starve_ms
        self._server: ModelServer | None = None

    def bind_server(self, server: ModelServer) -> None:
        self._server = server

    def select(self, queue: list[Request], k: int, now: float) -> list[Request]:
        warm = self._server.warm_free_streams() if self._server is not None else set()
        starved = [r for r in queue if now - r.ready_ms >= self.starve_ms]
        starved.sort(key=lambda r: r.ready_ms)
        fresh = [r for r in queue if now - r.ready_ms < self.starve_ms]
        fresh.sort(key=lambda r: (-r.waiters(), 0 if r.stream in warm else 1))
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
        self._server: ModelServer | None = None

    def bind_server(self, server: ModelServer) -> None:
        self._server = server

    def _views(self, queue: list[Request]) -> list[tracon_core.RequestView]:
        warm = self._server.warm_free_streams() if self._server is not None else set()
        return [
            tracon_core.RequestView(
                req=i,
                stream=self._streams.setdefault(r.stream, len(self._streams)),
                ready_ms=r.ready_ms,
                service_ms=r.service_ms,
                waiters=r.waiters(),
                warm=1 if r.stream in warm else 0,
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
        elif self._kernel == "affinity":
            picked = tracon_core.select_affinity(views, k, now, self._starve_ms)
        elif self._kernel == "tracon":
            picked = tracon_core.select_tracon(views, k, now, self._starve_ms)
        else:
            raise ValueError(f"unknown core kernel: {self._kernel}")
        return [queue[i] for i in picked]


class GrpcPolicy:
    """The core seam over the wire: identical views, selection by the Go service
    (``go/cmd/traconsvc``), which compiles the very same C++ kernels. Address
    comes from ``$TRACON_GRPC_ADDR`` (default 127.0.0.1:50351); the service must
    already be running."""

    def __init__(self, kernel: str, starve_ms: float = STARVE_MS) -> None:
        self.name = f"grpc-{kernel}"
        self._kernel = kernel
        self._starve_ms = starve_ms
        self._streams: dict[StreamKey, int] = {}
        self._server: ModelServer | None = None
        address = os.environ.get(GRPC_ADDR_ENV, GRPC_ADDR_DEFAULT)
        self._stub = scheduler_pb2_grpc.SchedulerStub(grpc.insecure_channel(address))

    def bind_server(self, server: ModelServer) -> None:
        self._server = server

    def select(self, queue: list[Request], k: int, now: float) -> list[Request]:
        warm = self._server.warm_free_streams() if self._server is not None else set()
        views = [
            scheduler_pb2.RequestView(
                req=i,
                stream=self._streams.setdefault(r.stream, len(self._streams)),
                ready_ms=r.ready_ms,
                service_ms=r.service_ms,
                waiters=r.waiters(),
                warm=1 if r.stream in warm else 0,
            )
            for i, r in enumerate(queue)
        ]
        request = scheduler_pb2.SelectRequest(
            kernel=self._kernel, queue=views, k=k, now=now, starve_ms=self._starve_ms
        )
        return [queue[i] for i in self._stub.Select(request).indices]


_PROTOTYPES = {
    "fifo": FIFOPolicy,
    "sjf": SJFPolicy,
    "unblock": UnblockPolicy,
    "affinity": AffinityPolicy,
    "tracon": TraconPolicy,
}


def make_policy(name: str) -> Policy:
    prototype = _PROTOTYPES.get(name)
    if prototype is not None:
        return prototype()
    if name.startswith("core-"):
        return CorePolicy(name.removeprefix("core-"))
    if name.startswith("grpc-"):
        return GrpcPolicy(name.removeprefix("grpc-"))
    raise ValueError(f"unknown policy: {name}")
