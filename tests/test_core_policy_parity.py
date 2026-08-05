"""Parity gates for the compiled core (docs/scheduler.md).

Every policy exists twice — Python prototype and C++ port. These tests prove the
two make identical decisions: at selection level on randomized queues, and through
full simulations where results must match byte-for-byte modulo the policy name.
"""

import random

from test_sim import _api, _prompt, _session, _write_events, chain_fixture

from tracon.sim.policies import (
    AffinityPolicy,
    FIFOPolicy,
    SJFPolicy,
    TraconPolicy,
    UnblockPolicy,
    make_policy,
)
from tracon.sim.runner import SimConfig, Simulation
from tracon.sim.server import Request
from tracon.sim.workload import build_workload


def _const(n: int):
    return lambda: n


def _queue(rng, n):
    """A ready-ordered queue (non-decreasing ready_ms, frequent ties)."""
    ready = 0.0
    queue = []
    for i in range(n):
        ready += rng.choice([0.0, 0.0, 1.0, 250.0])  # ties are the dangerous case
        queue.append(
            Request(
                req_id=f"r{i}",
                stream=(f"s{rng.randrange(4)}", None),
                service_ms=rng.choice([1.0, 40.0, 40.0, 9_000.0]),
                on_complete=lambda: None,
                ready_ms=ready,
                waiters=_const(rng.randrange(4)),
            )
        )
    return queue


def _ids(batch):
    return [r.req_id for r in batch]


class _FakeServer:
    """Just enough server for affinity-aware policies: a fixed warm-stream set."""

    def __init__(self, warm):
        self._warm = warm

    def warm_free_streams(self):
        return self._warm


def test_selection_parity_on_randomized_queues():
    rng = random.Random(2718)  # noqa: S311 — reproducible test data, not crypto
    for _ in range(300):
        queue = _queue(rng, rng.randrange(30))
        k = rng.randrange(9)
        # now at/after the newest request; large offsets push requests past the guard
        now = (queue[-1].ready_ms if queue else 0.0) + rng.choice([0.0, 500.0, 70_000.0])
        warm = {r.stream for r in queue if rng.random() < 0.4}
        pairs = [
            (FIFOPolicy(), make_policy("core-fifo")),
            (SJFPolicy(), make_policy("core-sjf")),
            (UnblockPolicy(), make_policy("core-unblock")),
            (AffinityPolicy(), make_policy("core-affinity")),
            (TraconPolicy(), make_policy("core-tracon")),
        ]
        for prototype, core in pairs:
            for policy in (prototype, core):
                bind = getattr(policy, "bind_server", None)
                if bind is not None:
                    bind(_FakeServer(warm))
            assert _ids(core.select(queue, k, now)) == _ids(prototype.select(queue, k, now))


def test_sjf_prototype_semantics():
    rng = random.Random(31415)  # noqa: S311 — reproducible test data, not crypto
    queue = _queue(rng, 6)
    for r, service in zip(queue, [500.0, 20.0, 20.0, 900.0, 5.0, 100.0], strict=True):
        r.service_ms = service
    now = queue[-1].ready_ms
    # no starvation: pure service order, ties keep queue order
    picked = SJFPolicy(starve_ms=1e12).select(queue, 3, now)
    assert _ids(picked) == ["r4", "r1", "r2"]
    # everyone starved: collapses to FIFO
    assert _ids(SJFPolicy(starve_ms=0.0).select(queue, 3, now)) == _ids(queue[:3])


def _contended_fixture(tmp_path):
    """Six one-step sessions arriving in bursts with mixed service times, so a
    single executor with batch 2 makes real (order-sensitive) choices."""
    events = []
    services = [30_000, 1_000, 15_000, 2_000, 45_000, 500]
    for i, service in enumerate(services):
        session = f"s{i}"
        arrive = (i // 2) * 1_000  # pairs arrive together: 0, 1s, 2s
        events += [
            _session(session),
            _prompt(session, arrive),
            _api(session, None, f"a{i}", arrive, service),
        ]
    _write_events(tmp_path, events)
    return build_workload(tmp_path / "events.jsonl")


def _run(workload, policy):
    config = SimConfig(executors=1, max_batch=2, max_wait_ms=100.0, policy=policy)
    results = Simulation(workload, config).run()
    results["config"]["policy"] = "-"  # the only field allowed to differ
    return results


def test_full_sim_parity_fifo(tmp_path):
    workload = _contended_fixture(tmp_path)
    assert _run(workload, "fifo") == _run(workload, "core-fifo")


def test_full_sim_parity_sjf(tmp_path):
    workload = _contended_fixture(tmp_path)
    python_results = _run(workload, "sjf")
    assert python_results == _run(workload, "core-sjf")
    # and SJF must actually schedule differently from FIFO here, or parity is vacuous
    assert python_results["turn_latency_ms"] != _run(workload, "fifo")["turn_latency_ms"]


def test_rerun_determinism(tmp_path):
    workload = _contended_fixture(tmp_path)
    assert _run(workload, "core-sjf") == _run(workload, "core-sjf")


def test_sync_spawn_child_counts_blocked_parent(tmp_path):
    workload = build_workload(chain_fixture(tmp_path) / "events.jsonl")
    sim = Simulation(workload, SimConfig(executors=None))
    sim.run()
    assert sim._runs["s1#ag1#t0"].blocked_waiters == 1


def _queued_turn_fixture(tmp_path):
    """B and C (30s each) arrive just before A's 10s turn; A's next turn is
    delivered at its traced time (10.2s), which lands mid-queue under contention."""
    events = [
        _session("s1"),
        _prompt("s1", 0),
        _api("s1", None, "b1", 0, 30_000),
        _session("s2"),
        _prompt("s2", 50),
        _api("s2", None, "c1", 50, 30_000),
        _session("s0"),
        _prompt("s0", 100),
        _api("s0", None, "a0", 100, 10_000),
        _prompt("s0", 10_200),
        _api("s0", None, "a1", 10_200, 1_000),
    ]
    _write_events(tmp_path, events)
    return build_workload(tmp_path / "events.jsonl")


def test_arrived_next_turn_counts_as_waiter(tmp_path):
    workload = _queued_turn_fixture(tmp_path)
    sim = Simulation(
        workload, SimConfig(executors=1, max_batch=1, max_wait_ms=0.0, policy="core-unblock")
    )
    sim.run()
    # A's second turn arrived (10.2s) while turn 0 was still queued behind B
    assert sim._runs["s0#main#t0"].blocked_waiters == 1


def test_unblock_beats_fifo_for_blocking_chains(tmp_path):
    workload = _queued_turn_fixture(tmp_path)

    def run(policy):
        config = SimConfig(executors=1, max_batch=1, max_wait_ms=0.0, policy=policy)
        return Simulation(workload, config).run()["turn_latency_ms"]

    fifo, unblock = run("fifo"), run("core-unblock")
    # unblock serves A's turn 0 before C (a queued turn waits on it): mean drops
    assert unblock["mean"] < fifo["mean"]
