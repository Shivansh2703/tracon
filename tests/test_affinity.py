"""Context-affinity backend + policies (docs/m4_plan.md, phase D).

Executors hold an LRU of resident stream contexts; cold placement costs
``cold_penalty_ms``. With the default penalty of 0 the backend must reproduce the
milestone-3 model exactly — that equivalence is covered by the untouched M3 tests
and the standing fidelity gate.
"""

from test_sim import _api, _prompt, _session, _write_events

from tracon.sim.engine import Engine
from tracon.sim.policies import FIFOPolicy
from tracon.sim.runner import SimConfig, Simulation
from tracon.sim.server import ModelServer, Request
from tracon.sim.workload import build_workload


def _server(engine, executors=1, penalty=5_000.0, resident=4):
    return ModelServer(
        engine,
        FIFOPolicy(),
        executors=executors,
        max_batch=1,
        max_wait_ms=0.0,
        cold_penalty_ms=penalty,
        resident_streams=resident,
    )


def _req(rid, stream, service, done):
    return Request(req_id=rid, stream=(stream, None), service_ms=service, on_complete=done)


def _submit_all(engine, server, reqs):
    def make_done(rid, finished):
        return lambda: finished.setdefault(rid, engine.now)

    finished = {}
    engine.at(
        0, lambda: [server.submit(_req(r, s, sv, make_done(r, finished))) for r, s, sv in reqs]
    )
    engine.run()
    return finished


def test_cold_penalty_then_warm_reuse():
    engine = Engine()
    server = _server(engine)
    finished = _submit_all(engine, server, [("a1", "A", 100), ("a2", "A", 100)])
    # a1 pays the 5s cold reload; a2 finds A resident and doesn't
    assert finished == {"a1": 5_100, "a2": 5_200}
    assert server.stats.cold_serves == 1
    assert server.stats.warm_serves == 1


def test_lru_eviction_recools_streams():
    engine = Engine()
    server = _server(engine, resident=1)
    finished = _submit_all(engine, server, [("a1", "A", 100), ("b1", "B", 100), ("a2", "A", 100)])
    # B evicts A from the single slot: all three serves are cold
    assert finished == {"a1": 5_100, "b1": 10_200, "a2": 15_300}
    assert server.stats.cold_serves == 3


def test_batch_lands_on_warm_executor():
    engine = Engine()
    server = _server(engine, executors=2)
    finished = {}
    engine.at(
        0,
        lambda: server.submit(_req("a1", "A", 100, lambda: finished.setdefault("a1", engine.now))),
    )
    # both executors free when a2 arrives; it must land on executor 0 where A is warm
    engine.at(
        10_000,
        lambda: server.submit(_req("a2", "A", 100, lambda: finished.setdefault("a2", engine.now))),
    )
    engine.run()
    assert finished == {"a1": 5_100, "a2": 10_100}  # a2 pays no cold penalty
    assert server.stats.warm_serves == 1


def test_warm_free_streams_only_reports_free_executors():
    engine = Engine()
    server = _server(engine)
    seen = {}
    engine.at(0, lambda: server.submit(_req("a1", "A", 1_000, lambda: None)))
    engine.at(100, lambda: seen.setdefault("busy", server.warm_free_streams()))
    engine.at(9_000, lambda: seen.setdefault("free", server.warm_free_streams()))
    engine.run()
    assert seen["busy"] == set()  # A is resident but its executor is occupied
    assert seen["free"] == {("A", None)}


def _interleaved_fixture(tmp_path):
    """Two sessions, two 1s turns each, all arriving within 30ms. When A's second
    turn unblocks it lands in the queue next to B's first — the choice point where
    affinity picks the warm stream and FIFO alternates contexts."""
    events = [
        _session("A"),
        _session("B"),
        _prompt("A", 0),
        _api("A", None, "a1", 0, 1_000),
        _prompt("B", 10),
        _api("B", None, "b1", 10, 1_000),
        _prompt("A", 20),
        _api("A", None, "a2", 20, 1_000),
        _prompt("B", 30),
        _api("B", None, "b2", 30, 1_000),
    ]
    _write_events(tmp_path, events)
    return build_workload(tmp_path / "events.jsonl")


def test_affinity_policy_reduces_cold_serves(tmp_path):
    workload = _interleaved_fixture(tmp_path)

    def run(policy):
        config = SimConfig(
            executors=1,
            max_batch=1,
            max_wait_ms=0.0,
            policy=policy,
            cold_penalty_ms=30_000.0,
            resident_streams=1,
        )
        return Simulation(workload, config).run()

    fifo = run("fifo")
    affinity = run("core-affinity")
    assert affinity["context"]["cold_serves"] < fifo["context"]["cold_serves"]
    assert affinity["turn_latency_ms"]["mean"] < fifo["turn_latency_ms"]["mean"]


def test_tracon_full_sim_parity_and_determinism(tmp_path):
    workload = _interleaved_fixture(tmp_path)

    def run(policy):
        config = SimConfig(
            executors=1,
            max_batch=2,
            max_wait_ms=50.0,
            policy=policy,
            cold_penalty_ms=8_000.0,
            resident_streams=1,
        )
        results = Simulation(workload, config).run()
        results["config"]["policy"] = "-"
        return results

    assert run("tracon") == run("core-tracon")
    assert run("core-tracon") == run("core-tracon")
    assert run("affinity") == run("core-affinity")
