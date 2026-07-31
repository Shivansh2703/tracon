"""Replication load harness (docs/m4_plan.md, phase C): R phase-offset copies of
the workload as independent sessions — the load knob for the policy comparison."""

from test_sim import chain_fixture

from tracon.sim.runner import SimConfig, Simulation
from tracon.sim.workload import build_workload, replicate_workload


def test_replicate_copies_streams_with_offsets(tmp_path):
    base = build_workload(chain_fixture(tmp_path) / "events.jsonl")
    tripled = replicate_workload(base, 3)

    assert len(tripled.turns) == 3 * len(base.turns)
    assert ("r1:s1", None) in tripled.turns_by_stream
    assert ("r2:s1", "ag1") in tripled.spawned_turns
    # replica turns shift by one offset per replica, uniform over the trace span
    span = max(t.arrival_ms for t in base.clock_turns)
    for tag in ("r1", "r2"):
        replica = tripled.turns_by_stream[(f"{tag}:s1", None)]
        offsets = [
            r.arrival_ms - b.arrival_ms for r, b in zip(replica, base.clock_turns, strict=True)
        ]
        assert max(offsets) - min(offsets) < 1e-6  # rigid shift: spacing preserved
        assert all(0.0 <= o < span for o in offsets)
    # the replica's spawn edge points at the replica's agent stream, not the original
    spawn_turn = tripled.turns_by_stream[("r1:s1", None)][0]
    spawned = [t.spawned_stream for s in spawn_turn.steps for t in s.tools if t.spawned_stream]
    assert spawned == [("r1:s1", "ag1")]


def test_replicate_is_deterministic_and_identity_at_one(tmp_path):
    base = build_workload(chain_fixture(tmp_path) / "events.jsonl")
    assert replicate_workload(base, 1) is base
    once = replicate_workload(base, 4)
    twice = replicate_workload(base, 4)
    assert [t.arrival_ms for t in once.turns] == [t.arrival_ms for t in twice.turns]
    assert [t.turn_id for t in once.turns] == [t.turn_id for t in twice.turns]


def test_replicated_workload_keeps_fidelity_at_infinite_capacity(tmp_path):
    """Each replica must reproduce its traced latencies exactly — the copy is only
    correct if the fidelity gate holds on the replicated workload too."""
    base = build_workload(chain_fixture(tmp_path) / "events.jsonl")
    results = Simulation(replicate_workload(base, 3), SimConfig(executors=None)).run()
    assert results["turns_completed"] == 6
    assert results["turns_incomplete"] == 0
    assert results["fidelity"]["abs_rel_error"]["max"] == 0.0


def test_replication_raises_contention(tmp_path):
    """More independent sessions on the same executor: queue waits must grow."""
    base = build_workload(chain_fixture(tmp_path) / "events.jsonl")
    config = SimConfig(executors=1, max_batch=1, max_wait_ms=0.0)
    native = Simulation(base, config).run()
    loaded = Simulation(replicate_workload(base, 6), config).run()
    assert loaded["queue_wait_ms"]["max"] >= native["queue_wait_ms"]["max"]
    assert loaded["utilization"] > native["utilization"]
