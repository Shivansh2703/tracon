"""Seam overhead microbench: the same tracon-kernel selection in-process
(pybind11) vs over the wire (Go gRPC service).

Usage: start the service (``go/bin/traconsvc``), then
``uv run python scripts/bench_seam.py``. Prints µs/call medians — the honest
per-decision cost of running the scheduler out of process.
"""

import os
import statistics
import time

import grpc
import tracon_core

from tracon.schedpb import scheduler_pb2, scheduler_pb2_grpc

DEPTHS = [10, 64, 256, 1024]
ITERS = 2_000
STARVE_MS = 60_000.0


def _views_py(n):
    return [
        tracon_core.RequestView(
            req=i, stream=i % 7, ready_ms=float(i), service_ms=float((i * 37) % 900), waiters=i % 3
        )
        for i in range(n)
    ]


def _views_pb(n):
    return [
        scheduler_pb2.RequestView(
            req=i, stream=i % 7, ready_ms=float(i), service_ms=float((i * 37) % 900), waiters=i % 3
        )
        for i in range(n)
    ]


def _bench(fn, iters=ITERS):
    fn()  # warm-up
    samples = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1e6)
    return statistics.median(samples), statistics.quantiles(samples, n=100)[94]


def main() -> None:
    address = os.environ.get("TRACON_GRPC_ADDR", "127.0.0.1:50351")
    stub = scheduler_pb2_grpc.SchedulerStub(grpc.insecure_channel(address))
    print("| queue depth | pybind11 µs/call (p50/p95) | gRPC µs/call (p50/p95) |")
    print("|---|---|---|")
    for depth in DEPTHS:
        views_py, views_pb = _views_py(depth), _views_pb(depth)
        py50, py95 = _bench(lambda v=views_py: tracon_core.select_tracon(v, 8, 1e6, STARVE_MS))
        request = scheduler_pb2.SelectRequest(
            kernel="tracon", queue=views_pb, k=8, now=1e6, starve_ms=STARVE_MS
        )
        g50, g95 = _bench(lambda r=request: stub.Select(r))
        print(f"| {depth} | {py50:.1f} / {py95:.1f} | {g50:.1f} / {g95:.1f} |")


if __name__ == "__main__":
    main()
