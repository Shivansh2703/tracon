import json
from pathlib import Path

from tracon.sim.engine import Engine
from tracon.sim.policies import FIFOPolicy
from tracon.sim.runner import SimConfig, Simulation, simulate
from tracon.sim.server import ModelServer, Request
from tracon.sim.workload import build_workload

BASE = 1_750_000_000_000


def test_engine_orders_and_ties_deterministic():
    engine = Engine()
    seen = []
    engine.at(20, lambda: seen.append("b"))
    engine.at(10, lambda: seen.append("a"))
    engine.at(20, lambda: seen.append("c"))  # same time: submission order wins
    engine.run()
    assert seen == ["a", "b", "c"]
    assert engine.now == 20


def _req(rid, service, done):
    return Request(req_id=rid, stream=("s", None), service_ms=service, on_complete=done)


def test_server_batches_by_size_and_completes_at_max_service():
    engine = Engine()
    server = ModelServer(engine, FIFOPolicy(), executors=1, max_batch=2, max_wait_ms=5.0)
    finished = {}

    def make_done(rid):
        return lambda: finished.setdefault(rid, engine.now)

    def submit_all():
        for rid, service in (("a", 100), ("b", 300), ("c", 50)):
            server.submit(_req(rid, service, make_done(rid)))

    engine.at(0, submit_all)
    engine.run()
    # queue fills to max_batch → [a,b] dispatch at 0, run to 300 (max member);
    # c waits for the executor and dispatches at 300, done 350
    assert finished == {"a": 300, "b": 300, "c": 350}
    assert server.stats.batch_sizes == [2, 1]
    assert server.stats.queue_waits == [0.0, 0.0, 300.0]


def test_server_waits_for_batch_window():
    engine = Engine()
    server = ModelServer(engine, FIFOPolicy(), executors=1, max_batch=4, max_wait_ms=25.0)
    finished = {}
    engine.at(
        0, lambda: server.submit(_req("a", 100, lambda: finished.setdefault("a", engine.now)))
    )
    engine.at(
        10, lambda: server.submit(_req("b", 100, lambda: finished.setdefault("b", engine.now)))
    )
    engine.run()
    # neither fills the batch; dispatch fires at a's deadline (25), both finish at 125
    assert finished == {"a": 125, "b": 125}
    assert server.stats.batch_sizes == [2]


def test_server_infinite_capacity_never_queues():
    engine = Engine()
    server = ModelServer(engine, FIFOPolicy(), executors=None, max_batch=8, max_wait_ms=10.0)
    finished = {}
    for rid in ("a", "b", "c"):
        engine.at(
            0,
            lambda r=rid: server.submit(
                _req(r, 100, lambda r=r: finished.setdefault(r, engine.now))
            ),
        )
    engine.run()
    assert finished == {"a": 100, "b": 100, "c": 100}
    assert server.stats.queue_waits == [0.0, 0.0, 0.0]


def _write_events(path: Path, events: list[dict]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "events.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
    )


def _api(session, agent, uuid, ts, span):
    return {
        "ev": "api_call",
        "session": session,
        "agent": agent,
        "ts": BASE + ts,
        "ts_last": BASE + ts + span,
        "uuid": uuid,
        "blocks": {"tool_use": 0},
        "usage": {},
    }


def _tool(session, agent, api_uuid, tid, ts, dur, spawned=None, background=False):
    return {
        "ev": "tool_call",
        "session": session,
        "agent": agent,
        "ts": BASE + ts,
        "ts_result": BASE + ts + dur,
        "duration_ms": dur,
        "id": tid,
        "name": "Bash",
        "api_uuid": api_uuid,
        "status": "matched",
        "background": background,
        "spawned_agent": spawned,
    }


def _prompt(session, ts):
    return {"ev": "prompt", "session": session, "agent": None, "ts": BASE + ts, "sidechain": False}


def _session(session, agent=None, t_start=0, t_end=100_000, background=False):
    return {
        "ev": "session",
        "session": session,
        "agent": agent,
        "ts": BASE + t_start,
        "t_start": BASE + t_start,
        "t_end": BASE + t_end,
        "background": background,
    }


def chain_fixture(tmp_path) -> Path:
    """One session, two turns; turn 0 is: model(1s) → [tool 4s ∥ sync agent] → model(1s).
    The agent chain is model(2s) → tool(3s) → model(1s) = 6s, so the join waits 6s.
    Turn 0 total = 1 + 6 + 1 = 8s. Turn 1 (arrives 60s): model(2s) = 2s."""
    events = [
        _session("s1"),
        _session("s1", agent="ag1", t_start=1_000),
        _prompt("s1", 0),
        _api("s1", None, "a1", 0, 1_000),
        _tool("s1", None, "a1", "t1", 1_000, 4_000),
        _tool("s1", None, "a1", "t2", 1_000, 6_000, spawned="ag1"),
        _api("s1", None, "a2", 7_000, 1_000),
        _prompt("s1", 60_000),
        _api("s1", None, "a3", 60_000, 2_000),
        # the agent's own chain
        _api("s1", "ag1", "b1", 1_000, 2_000),
        _tool("s1", "ag1", "b1", "t3", 3_000, 3_000),
        _api("s1", "ag1", "b2", 6_000, 1_000),
    ]
    _write_events(tmp_path, events)
    return tmp_path


def test_workload_builder_chain(tmp_path):
    workload = build_workload(chain_fixture(tmp_path) / "events.jsonl")
    assert len(workload.turns_by_stream[("s1", None)]) == 2
    turn0, turn1 = workload.turns_by_stream[("s1", None)]
    assert [s.service_ms for s in turn0.steps] == [1_000.0, 1_000.0]
    assert len(turn0.steps[0].tools) == 2
    spawn = next(t for t in turn0.steps[0].tools if t.spawned_stream)
    assert spawn.spawned_stream == ("s1", "ag1")
    assert turn0.traced_latency_ms == 8_000.0
    assert turn1.arrival_ms == 60_000.0
    agent_turn = workload.spawned_turns[("s1", "ag1")]
    assert [s.service_ms for s in agent_turn.steps] == [2_000.0, 1_000.0]


def test_simulation_infinite_capacity_reproduces_chain(tmp_path):
    workload = build_workload(chain_fixture(tmp_path) / "events.jsonl")
    results = Simulation(workload, SimConfig(executors=None)).run()
    assert results["turns_completed"] == 2
    assert results["turns_incomplete"] == 0
    # turn latencies: 8s and 2s exactly
    assert results["turn_latency_ms"]["max"] == 8_000.0
    assert results["turn_latency_ms"]["p50"] == 2_000.0
    assert results["agent_runs"] == 1
    assert results["agent_latency_ms"]["max"] == 6_000.0
    assert results["fidelity"]["abs_rel_error"]["max"] == 0.0


def test_gaps_are_replayed_as_exogenous_delay(tmp_path):
    """Dead time in the traced timeline (permission waits, retries, sleep) must
    survive replay: prompt at 0, model call only starts at 5s, runs 1s → latency 6s."""
    events = [
        _session("s1"),
        _prompt("s1", 0),
        _api("s1", None, "a1", 5_000, 1_000),
        _api("s1", None, "a2", 8_000, 1_000),  # 2s gap after a1 ends at 6s
    ]
    _write_events(tmp_path, events)
    workload = build_workload(tmp_path / "events.jsonl")
    turn = workload.turns_by_stream[("s1", None)][0]
    assert [s.pre_gap_ms for s in turn.steps] == [5_000.0, 2_000.0]
    results = Simulation(workload, SimConfig(executors=None)).run()
    assert results["turn_latency_ms"]["max"] == 9_000.0
    assert results["fidelity"]["abs_rel_error"]["max"] == 0.0


def test_simulation_contention_delays_turns(tmp_path):
    """Two sessions arriving together with 10s model steps on one executor
    (batch 1): the second serializes behind the first."""
    events = [
        _session("s1"),
        _session("s2"),
        _prompt("s1", 0),
        _api("s1", None, "a1", 0, 10_000),
        _prompt("s2", 0),
        {**_api("s2", None, "z1", 0, 10_000), "session": "s2"},
    ]
    _write_events(tmp_path, events)
    workload = build_workload(tmp_path / "events.jsonl")
    results = Simulation(workload, SimConfig(executors=1, max_batch=1, max_wait_ms=0.0)).run()
    latencies = results["turn_latency_ms"]
    assert latencies["p50"] == 10_000.0
    assert latencies["max"] == 20_000.0
    assert results["queue_wait_ms"]["max"] == 10_000.0
    assert results["utilization"] == 1.0


def test_agent_continuations_do_not_gate_spawn(tmp_path):
    """A seat agent continued via an injected prompt: the parent's sync spawn waits
    only on the agent's first turn, not its whole lifetime."""
    events = [
        _session("s1"),
        _session("s1", agent="ag1", t_start=2_000),
        _prompt("s1", 0),
        _api("s1", None, "a1", 0, 1_000),
        _tool("s1", None, "a1", "t1", 1_000, 3_000, spawned="ag1"),
        # agent turn 0: model 2s → parent join at 4s
        _api("s1", "ag1", "b1", 2_000, 2_000),
        # continuation prompt an hour later, injected into the agent
        {
            "ev": "prompt",
            "session": "s1",
            "agent": "ag1",
            "ts": BASE + 3_600_000,
            "sidechain": True,
        },
        _api("s1", "ag1", "b2", 3_600_000, 5_000),
    ]
    _write_events(tmp_path, events)
    workload = build_workload(tmp_path / "events.jsonl")
    agent_turns = workload.turns_by_stream[("s1", "ag1")]
    assert len(agent_turns) == 2
    assert agent_turns[0].spawned is True
    assert agent_turns[1].spawned is False

    results = Simulation(workload, SimConfig(executors=None)).run()
    # parent turn: 1s model + 3s child wait = 4s, NOT 1h+
    assert results["turn_latency_ms"]["max"] == 4_000.0
    assert results["agent_runs"] == 2
    assert results["turns_incomplete"] == 0


def test_defacto_background_spawn_reclassified(tmp_path):
    """An async launch that doesn't set run_in_background: traced spawn ack is 10ms
    while the child chain runs 100s. The parent must not gate on the child."""
    events = [
        _session("s1"),
        _session("s1", agent="ag1", t_start=1_010),
        _prompt("s1", 0),
        _api("s1", None, "a1", 0, 1_000),
        _tool("s1", None, "a1", "t1", 1_000, 10, spawned="ag1"),  # 10ms ack
        _api("s1", None, "a2", 1_010, 1_000),
        _api("s1", "ag1", "b1", 1_010, 100_000),
    ]
    _write_events(tmp_path, events)
    workload = build_workload(tmp_path / "events.jsonl")
    assert workload.skipped.get("spawn_reclassified_background") == 1
    results = Simulation(workload, SimConfig(executors=None)).run()
    # parent turn: 1s model + 10ms ack + 1s model, NOT +100s child wait
    assert results["turn_latency_ms"]["max"] == 2_010.0
    assert results["agent_runs"] == 1
    # child chain includes its 10ms spawn-startup pre-gap
    assert results["agent_latency_ms"]["max"] == 100_010.0


def test_resumed_preprompt_work_is_own_turn(tmp_path):
    """Main-stream APIs before the first prompt (resumed session tail) must not
    merge into the next prompt's turn."""
    events = [
        _session("s1"),
        _api("s1", None, "a0", 0, 1_000),  # resumed tail work, no prompt yet
        _prompt("s1", 3_600_000),
        _api("s1", None, "a1", 3_600_000, 2_000),
    ]
    _write_events(tmp_path, events)
    workload = build_workload(tmp_path / "events.jsonl")
    turns = workload.turns_by_stream[("s1", None)]
    assert len(turns) == 2
    assert turns[0].arrival_ms == 0.0
    assert turns[1].arrival_ms == 3_600_000.0
    results = Simulation(workload, SimConfig(executors=None)).run()
    # latencies 1s and 2s — not one turn measured from the resumed tail
    assert results["turn_latency_ms"]["max"] == 2_000.0


def test_sync_spawn_overhead_enforced(tmp_path):
    """Traced spawn wait (7s) exceeds the child chain (6s): the 1s notification
    overhead must be replayed, or the parent finishes early (codex finding #2)."""
    events = [
        _session("s1"),
        _session("s1", agent="ag1", t_start=1_000),
        _prompt("s1", 0),
        _api("s1", None, "a1", 0, 1_000),
        _tool("s1", None, "a1", "t1", 1_000, 7_000, spawned="ag1"),
        _api("s1", "ag1", "b1", 1_000, 6_000),
    ]
    _write_events(tmp_path, events)
    workload = build_workload(tmp_path / "events.jsonl")
    spawn = workload.turns_by_stream[("s1", None)][0].steps[0].tools[0]
    assert spawn.overhead_ms == 1_000.0
    results = Simulation(workload, SimConfig(executors=None)).run()
    assert results["turn_latency_ms"]["max"] == 8_000.0  # 1s model + 6s child + 1s overhead
    assert results["fidelity"]["abs_rel_error"]["max"] == 0.0


def test_stale_batch_timer_does_not_inflate_makespan(tmp_path):
    """A wait timer left over after the queue filled must not count as makespan
    (codex finding #4: utilization 0.1 instead of 1.0)."""
    events = [
        _session("s1"),
        _session("s2"),
        _prompt("s1", 0),
        _api("s1", None, "a1", 0, 1),
        _prompt("s2", 0),
        _api("s2", None, "z1", 0, 1),
    ]
    _write_events(tmp_path, events)
    workload = build_workload(tmp_path / "events.jsonl")
    results = Simulation(workload, SimConfig(executors=1, max_batch=2, max_wait_ms=10.0)).run()
    assert results["utilization"] == 1.0


def test_agent_with_only_continuation_does_not_gate_parent(tmp_path):
    """First agent activity follows a later injected prompt: reconciliation flips
    the spawn to background (traced wait 500ms vs hours), so the parent proceeds
    after the traced delay instead of waiting through the continuation."""
    events = [
        _session("s1"),
        _session("s1", agent="ag1", t_start=1_000),
        _prompt("s1", 0),
        _api("s1", None, "a1", 0, 1_000),
        _tool("s1", None, "a1", "t1", 1_000, 500, spawned="ag1"),
        {
            "ev": "prompt",
            "session": "s1",
            "agent": "ag1",
            "ts": BASE + 3_600_000,
            "sidechain": True,
        },
        _api("s1", "ag1", "b1", 3_600_000, 2_000),
    ]
    _write_events(tmp_path, events)
    workload = build_workload(tmp_path / "events.jsonl")
    assert workload.skipped.get("spawn_reclassified_background") == 1
    results = Simulation(workload, SimConfig(executors=None)).run()
    assert results["turn_latency_ms"]["max"] == 1_500.0  # model 1s + traced delay 500ms
    assert results["turns_incomplete"] == 0
    assert results["agents_incomplete"] == 0


def test_malformed_events_do_not_crash(tmp_path):
    """Null prompt timestamps are skipped; backward ts_last doesn't corrupt gaps."""
    events = [
        _session("s1"),
        {"ev": "prompt", "session": "s1", "agent": None, "ts": None, "sidechain": False},
        _prompt("s1", 0),
        {**_api("s1", None, "a1", 100, 0), "ts_last": BASE + 50},  # backward ts_last
        _api("s1", None, "a2", 110, 10),
    ]
    _write_events(tmp_path, events)
    workload = build_workload(tmp_path / "events.jsonl")
    assert workload.skipped.get("prompt_no_ts") == 1
    turn = workload.turns_by_stream[("s1", None)][0]
    # gap to a2 measured from a1's ts (100), not its backward ts_last (50)
    assert turn.steps[1].pre_gap_ms == 10.0


def test_simulate_end_to_end(tmp_path):
    chain_fixture(tmp_path)
    results = simulate(tmp_path, SimConfig(executors=2, max_batch=4, max_wait_ms=5.0))
    assert results["turns_completed"] == 2
    assert results["turns_incomplete"] == 0
    assert results["batches"]["dispatches"] >= 3
