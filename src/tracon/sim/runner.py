"""Replay a workload through the simulated backend and measure it.

Turns are released at their traced arrival times (optionally time-compressed to
raise load); a main stream's next turn additionally waits for its previous turn's
chain to finish. Model steps queue on the shared backend; tool delays elapse in
simulated time; sync agent spawns block their parent tool until the child chain
completes, background spawns only consume backend capacity.

Validation mode (``executors=None``, compress 1.0): with no queueing or batching,
simulated turn latency must reproduce the traced latency — the reported fidelity
error is the modeling error floor under every policy comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any

from tracon.sim.engine import Engine
from tracon.sim.policies import make_policy
from tracon.sim.server import ModelServer, Request
from tracon.sim.workload import StreamKey, Turn, Workload, build_workload, replicate_workload
from tracon.trace.characterize import dist


@dataclass
class SimConfig:
    executors: int | None = 1  # None = infinite capacity (validation mode)
    max_batch: int = 8
    max_wait_ms: float = 10.0
    time_compress: float = 1.0
    policy: str = "fifo"
    replicate: int = 1  # workload copies with phase offsets (the load knob)


@dataclass
class _TurnRun:
    turn: Turn
    gates: int
    prev: _TurnRun | None = None
    started_ms: float | None = None
    completion_ms: float | None = None
    pending_tools: int = 0
    waiters: list[Any] = field(default_factory=list)
    # chains demonstrably blocked on this one: a same-stream next turn whose clock
    # arrival already fired, or a parent gated on this sync spawn. Direct counts
    # only — no transitive closure through spawn trees (documented limitation).
    blocked_waiters: int = 0


class Simulation:
    def __init__(self, workload: Workload, config: SimConfig) -> None:
        self._workload = workload
        self._config = config
        self._engine = Engine()
        self._server = ModelServer(
            self._engine,
            make_policy(config.policy),
            executors=config.executors,
            max_batch=config.max_batch,
            max_wait_ms=config.max_wait_ms,
        )
        self._runs: dict[str, _TurnRun] = {}
        self._referenced: set[StreamKey] = {
            tool.spawned_stream
            for turn in workload.turns
            for step in turn.steps
            for tool in step.tools
            if tool.spawned_stream is not None
        }

    def _arrival(self, turn: Turn) -> float:
        return turn.arrival_ms / self._config.time_compress

    def run(self) -> dict[str, Any]:
        for stream_turns in self._workload.turns_by_stream.values():
            prev: _TurnRun | None = None
            for turn in stream_turns:
                clock_released = not turn.spawned or turn.stream not in self._referenced
                gates = (1 if clock_released else 0) + (1 if prev is not None else 0)
                # a spawned turn waits only for its parent's launch (1 implicit gate)
                run = _TurnRun(turn=turn, gates=max(gates, 1), prev=prev)
                self._runs[turn.turn_id] = run
                if prev is not None:
                    prev.waiters.append(partial(self._open_gate, run))
                if clock_released:
                    self._engine.at(self._arrival(turn), partial(self._clock_arrival, run))
                prev = run
        self._engine.run()
        return self._results()

    def _clock_arrival(self, run: _TurnRun) -> None:
        self._open_gate(run)
        if run.started_ms is None and run.prev is not None and run.prev.completion_ms is None:
            run.prev.blocked_waiters += 1  # arrived, but queued behind its own stream

    def _open_gate(self, run: _TurnRun) -> None:
        run.gates -= 1
        if run.gates == 0 and run.started_ms is None:
            run.started_ms = self._engine.now
            self._start_step(run, 0)

    def _start_step(self, run: _TurnRun, index: int) -> None:
        step = run.turn.steps[index]
        request = Request(
            req_id=f"{run.turn.turn_id}/{index}",
            stream=run.turn.stream,
            service_ms=step.service_ms,
            on_complete=partial(self._model_done, run, index),
            waiters=partial(self._blocked_waiters, run),
        )
        if step.pre_gap_ms > 0:  # traced client-side dead time before issuing
            self._engine.after(step.pre_gap_ms, partial(self._server.submit, request))
        else:
            self._server.submit(request)

    def _model_done(self, run: _TurnRun, index: int) -> None:
        tools = run.turn.steps[index].tools
        if not tools:
            self._step_finished(run, index)
            return
        run.pending_tools = len(tools)
        for tool in tools:
            done = partial(self._tool_done, run, index)
            if tool.spawned_stream is not None:
                spawn_turn = self._workload.spawned_turns.get(tool.spawned_stream)
                child = self._runs.get(spawn_turn.turn_id) if spawn_turn is not None else None
                if child is not None:
                    if tool.background:
                        self._launch_child(child)
                        self._engine.after(tool.duration_ms, done)
                    else:
                        # parent resumes at child completion plus the traced
                        # notification/return overhead beyond the child's chain
                        child.blocked_waiters += 1  # the parent is provably waiting
                        if tool.overhead_ms > 0:
                            child.waiters.append(
                                partial(self._engine.after, tool.overhead_ms, done)
                            )
                        else:
                            child.waiters.append(done)
                        self._launch_child(child)
                    continue
            self._engine.after(tool.duration_ms, done)

    @staticmethod
    def _blocked_waiters(run: _TurnRun) -> int:
        return run.blocked_waiters

    def _launch_child(self, child: _TurnRun) -> None:
        if child.started_ms is None and child.completion_ms is None:
            self._open_gate(child)

    def _tool_done(self, run: _TurnRun, index: int) -> None:
        run.pending_tools -= 1
        if run.pending_tools == 0:
            self._step_finished(run, index)

    def _step_finished(self, run: _TurnRun, index: int) -> None:
        if index + 1 < len(run.turn.steps):
            self._start_step(run, index + 1)
        else:
            run.completion_ms = self._engine.now
            for waiter in run.waiters:
                waiter()

    def _results(self) -> dict[str, Any]:
        config = self._config
        turn_latencies: list[float] = []
        agent_latencies: list[float] = []
        rel_errors: list[float] = []
        incomplete = 0
        agents_incomplete = 0
        last_completion = 0.0
        for run in self._runs.values():
            if run.completion_ms is None:
                if run.turn.stream[1] is not None:
                    agents_incomplete += 1
                else:
                    incomplete += 1
                continue
            last_completion = max(last_completion, run.completion_ms)
            if run.turn.stream[1] is not None:  # agent stream: spawn or continuation
                if run.started_ms is not None:
                    agent_latencies.append(run.completion_ms - run.started_ms)
                continue
            latency = run.completion_ms - self._arrival(run.turn)
            turn_latencies.append(latency)
            traced = run.turn.traced_latency_ms
            if (
                config.executors is None
                and config.time_compress == 1.0
                and traced is not None
                and traced > 0
            ):
                rel_errors.append(abs(latency - traced) / traced)

        stats = self._server.stats
        # last real completion, not engine.now — a stale batch timer can tick
        # after all work is done and would inflate makespan / depress utilization
        makespan = last_completion
        utilization = None
        if config.executors is not None and makespan > 0:
            utilization = round(stats.busy_ms / (makespan * config.executors), 3)
        fidelity = None
        if rel_errors:
            fidelity = {
                "turns_compared": len(rel_errors),
                "abs_rel_error": dist([round(e, 4) for e in rel_errors]),
            }
        return {
            "config": {
                "executors": config.executors,
                "max_batch": config.max_batch,
                "max_wait_ms": config.max_wait_ms,
                "time_compress": config.time_compress,
                "policy": config.policy,
                "replicate": config.replicate,
            },
            "turns_completed": len(turn_latencies),
            "turns_incomplete": incomplete,
            "agents_incomplete": agents_incomplete,
            "turn_latency_ms": dist(turn_latencies),
            "agent_runs": len(agent_latencies),
            "agent_latency_ms": dist(agent_latencies),
            "queue_wait_ms": dist(stats.queue_waits),
            "batches": {
                "dispatches": stats.dispatches,
                "mean_size": round(stats.batched_requests / stats.dispatches, 2)
                if stats.dispatches
                else 0,
            },
            "utilization": utilization,
            "makespan_hours": round(makespan / 3_600_000, 2),
            "fidelity": fidelity,
            "workload_skipped": self._workload.skipped,
        }


def simulate(traces_dir: Path, config: SimConfig) -> dict[str, Any]:
    workload = replicate_workload(build_workload(traces_dir / "events.jsonl"), config.replicate)
    return Simulation(workload, config).run()
