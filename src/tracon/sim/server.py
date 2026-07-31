"""Simulated model backend: parallel batch executors with dynamic batching.

Triton-style front end: requests queue as they become ready; an executor takes a
batch when the queue reaches ``max_batch`` or the oldest request has waited
``max_wait_ms``. A batch occupies its executor for the max member service time and
all members complete together. ``executors=None`` models infinite capacity (every
request served alone, immediately) — the validation mode.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tracon.sim.engine import Engine
    from tracon.sim.policies import Policy
    from tracon.sim.workload import StreamKey


def _no_waiters() -> int:
    return 0


@dataclass
class Request:
    req_id: str
    stream: StreamKey
    service_ms: float
    on_complete: Callable[[], None]
    ready_ms: float = 0.0
    start_ms: float | None = None
    finish_ms: float | None = None
    # live count of chains blocked on this request's completion (runner-provided,
    # read at selection time — a prompt queued after submit must still be seen)
    waiters: Callable[[], int] = _no_waiters

    @property
    def queue_wait_ms(self) -> float:
        return (self.start_ms or self.ready_ms) - self.ready_ms


@dataclass
class ServerStats:
    dispatches: int = 0
    batched_requests: int = 0
    busy_ms: float = 0.0
    queue_waits: list[float] = field(default_factory=list)
    batch_sizes: list[int] = field(default_factory=list)


class ModelServer:
    def __init__(
        self,
        engine: Engine,
        policy: Policy,
        executors: int | None,
        max_batch: int,
        max_wait_ms: float,
    ) -> None:
        self._engine = engine
        self._policy = policy
        self._executors = executors
        self._max_batch = max(1, max_batch)
        self._max_wait_ms = max_wait_ms
        self._free = executors if executors is not None else 0
        self._queue: list[Request] = []
        self._timer_at: float | None = None
        self.stats = ServerStats()

    def submit(self, request: Request) -> None:
        request.ready_ms = self._engine.now
        if self._executors is None:  # infinite capacity: no queueing, no batching
            request.start_ms = self._engine.now
            self.stats.dispatches += 1
            self.stats.batched_requests += 1
            self.stats.batch_sizes.append(1)
            self.stats.queue_waits.append(0.0)
            self.stats.busy_ms += request.service_ms
            self._engine.after(request.service_ms, lambda: self._finish([request]))
            return
        self._queue.append(request)
        self._try_dispatch()

    def _try_dispatch(self) -> None:
        now = self._engine.now
        while self._free > 0 and self._queue:
            full = len(self._queue) >= self._max_batch
            oldest_wait = now - self._queue[0].ready_ms
            if not (full or oldest_wait >= self._max_wait_ms):
                deadline = self._queue[0].ready_ms + self._max_wait_ms
                if self._timer_at is None or self._timer_at > deadline:
                    self._timer_at = deadline
                    self._engine.at(deadline, self._on_timer)
                return
            batch = self._policy.select(self._queue, self._max_batch, now)
            for request in batch:
                self._queue.remove(request)
                request.start_ms = now
                self.stats.queue_waits.append(request.queue_wait_ms)
            self._free -= 1
            service = max(r.service_ms for r in batch)
            self.stats.dispatches += 1
            self.stats.batched_requests += len(batch)
            self.stats.batch_sizes.append(len(batch))
            self.stats.busy_ms += service
            self._engine.after(service, lambda b=batch: self._finish_and_free(b))

    def _on_timer(self) -> None:
        self._timer_at = None
        self._try_dispatch()

    def _finish_and_free(self, batch: list[Request]) -> None:
        self._free += 1
        self._finish(batch)
        self._try_dispatch()

    def _finish(self, batch: list[Request]) -> None:
        for request in batch:
            request.finish_ms = self._engine.now
            request.on_complete()
