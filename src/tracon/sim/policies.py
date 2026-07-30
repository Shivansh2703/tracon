"""Scheduling policies: given the ready queue, choose the next batch.

The baseline is FIFO — take the k oldest-ready requests, exactly what a
dynamic-batching front end does. Dependency- and session-aware policies
(milestone 4) implement the same protocol and reorder the queue instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from tracon.sim.server import Request


class Policy(Protocol):
    name: str

    def select(self, queue: list[Request], k: int) -> list[Request]:
        """Pick up to k requests from the ready queue (queue is ready-order)."""
        ...


class FIFOPolicy:
    name = "fifo"

    def select(self, queue: list[Request], k: int) -> list[Request]:
        return queue[:k]
