"""Simulated model backend: parallel batch executors with dynamic batching.

Triton-style front end: requests queue as they become ready; an executor takes a
batch when the queue reaches ``max_batch`` or the oldest request has waited
``max_wait_ms``. A batch occupies its executor for the max member service time and
all members complete together. ``executors=None`` models infinite capacity (every
request served alone, immediately) — the validation mode.

Context affinity (milestone 4): each executor holds an LRU of ``resident_streams``
stream contexts. A batch is placed on the free executor with the most warm members;
each cold member's service time grows by ``cold_penalty_ms`` (default 0, which
reproduces the milestone-3 backend exactly). Policies may ask the server which
streams are warm on a free executor via ``warm_free_streams``.
"""

from __future__ import annotations

from collections import OrderedDict
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
    warm_serves: int = 0
    cold_serves: int = 0
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
        cold_penalty_ms: float = 0.0,
        resident_streams: int = 4,
    ) -> None:
        self._engine = engine
        self._policy = policy
        self._executors = executors
        self._max_batch = max(1, max_batch)
        self._max_wait_ms = max_wait_ms
        self._cold_penalty_ms = cold_penalty_ms
        self._resident_cap = max(1, resident_streams)
        self._exec_free: list[bool] = [True] * (executors or 0)
        self._resident: list[OrderedDict[StreamKey, None]] = [
            OrderedDict() for _ in range(executors or 0)
        ]
        self._queue: list[Request] = []
        self._timer_at: float | None = None
        self.stats = ServerStats()

    def warm_free_streams(self) -> set[StreamKey]:
        """Streams whose context is resident on at least one currently-free executor."""
        return {
            stream
            for i, is_free in enumerate(self._exec_free)
            if is_free
            for stream in self._resident[i]
        }

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

    def _pick_executor(self, batch: list[Request]) -> int:
        """The free executor with the most warm batch members (ties: lowest index)."""
        free = [i for i, is_free in enumerate(self._exec_free) if is_free]
        return max(free, key=lambda i: sum(1 for r in batch if r.stream in self._resident[i]))

    def _batch_service(self, batch: list[Request], executor: int) -> float:
        service = 0.0
        for request in batch:
            warm = request.stream in self._resident[executor]
            if warm:
                self.stats.warm_serves += 1
            else:
                self.stats.cold_serves += 1
            penalty = 0.0 if warm else self._cold_penalty_ms
            service = max(service, request.service_ms + penalty)
        resident = self._resident[executor]
        for request in batch:  # contexts become MRU-resident as the batch loads
            resident[request.stream] = None
            resident.move_to_end(request.stream)
        while len(resident) > self._resident_cap:
            resident.popitem(last=False)
        return service

    def _try_dispatch(self) -> None:
        now = self._engine.now
        while any(self._exec_free) and self._queue:
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
            executor = self._pick_executor(batch)
            self._exec_free[executor] = False
            service = self._batch_service(batch, executor)
            self.stats.dispatches += 1
            self.stats.batched_requests += len(batch)
            self.stats.batch_sizes.append(len(batch))
            self.stats.busy_ms += service
            self._engine.after(service, lambda b=batch, e=executor: self._finish_and_free(b, e))

    def _on_timer(self) -> None:
        self._timer_at = None
        self._try_dispatch()

    def _finish_and_free(self, batch: list[Request], executor: int) -> None:
        self._exec_free[executor] = True
        self._finish(batch)
        self._try_dispatch()

    def _finish(self, batch: list[Request]) -> None:
        for request in batch:
            request.finish_ms = self._engine.now
            request.on_complete()
