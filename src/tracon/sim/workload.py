"""Rebuild schedulable jobs from exported trace events.

The unit of work is a **turn**: a human prompt (or an agent spawn) followed by a
sequential chain of model steps. Each model step occupies the model backend for its
traced service time, then launches the tool calls it issued; the next step becomes
ready when all of those tools complete. Tool calls are exogenous delays with traced
durations — except agent spawns, which release a child job whose own chain must
complete (sync) or which runs alongside (background, gating nothing but capacity).

The traced timestamps provide arrivals and, for validation, the actually-observed
turn latencies the simulator must reproduce at infinite capacity.
"""

from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

MIN_SERVICE_MS = 1.0
REPLICATE_SEED = 4  # fixed: replica phase offsets are part of the methodology

StreamKey = tuple[str, str | None]  # (session, agent-hex | None for the main stream)


@dataclass
class ToolStep:
    tool_id: str
    name: str
    duration_ms: float
    spawned_stream: StreamKey | None = None
    background: bool = False
    # sync spawns only: traced parent wait beyond the child's own chain
    # (notification/return overhead). The child chain stays policy-sensitive;
    # this fixed remainder is not.
    overhead_ms: float = 0.0


@dataclass
class ModelStep:
    step_id: str
    service_ms: float
    # traced dead time between the previous step's join and this request being
    # issued: permission-prompt waits, API retry/backoff, machine asleep. Exogenous —
    # no scheduling policy can compress it — but without it replay is 3x too fast.
    pre_gap_ms: float = 0.0
    tools: list[ToolStep] = field(default_factory=list)


@dataclass
class Turn:
    turn_id: str
    stream: StreamKey
    arrival_ms: float  # traced arrival, relative to workload t0
    steps: list[ModelStep]
    traced_latency_ms: float | None  # observed completion - arrival, for validation
    spawned: bool = False  # arrival is endogenous (agent turn), not a clock arrival
    background: bool = False


@dataclass
class Workload:
    turns: list[Turn]
    turns_by_stream: dict[StreamKey, list[Turn]]
    spawned_turns: dict[StreamKey, Turn]
    t0_ms: int
    skipped: dict[str, int]

    @property
    def clock_turns(self) -> list[Turn]:
        return [t for t in self.turns if not t.spawned]


def _stream_key(event: dict[str, Any]) -> StreamKey:
    return (event["session"], event.get("agent"))


class _Builder:
    def __init__(self) -> None:
        self.api_by_stream: dict[StreamKey, list[dict[str, Any]]] = defaultdict(list)
        self.tools_by_api: dict[tuple[StreamKey, str], list[dict[str, Any]]] = defaultdict(list)
        self.prompts_by_stream: dict[StreamKey, list[dict[str, Any]]] = defaultdict(list)
        self.sessions: dict[StreamKey, dict[str, Any]] = {}
        self.spawn_ts: dict[StreamKey, int] = {}
        self.skipped: dict[str, int] = defaultdict(int)

    def load(self, events_path: Path) -> None:
        with events_path.open(encoding="utf-8") as fh:
            for raw in fh:
                event = json.loads(raw)
                kind = event["ev"]
                if kind == "session":
                    self.sessions[_stream_key(event)] = event
                elif kind == "api_call":
                    if event.get("ts") is None:
                        self.skipped["api_no_ts"] += 1
                        continue
                    self.api_by_stream[_stream_key(event)].append(event)
                elif kind == "tool_call":
                    spawned = event.get("spawned_agent")
                    if spawned and event.get("ts") is not None:
                        # spawn-startup overhead becomes the child's first pre-gap
                        self.spawn_ts[(event["session"], spawned)] = event["ts"]
                    api_uuid = event.get("api_uuid")
                    if not api_uuid:
                        self.skipped["tool_unlinked"] += 1
                        continue
                    self.tools_by_api[(_stream_key(event), api_uuid)].append(event)
                elif kind == "prompt":
                    if event.get("ts") is None:
                        self.skipped["prompt_no_ts"] += 1
                        continue
                    self.prompts_by_stream[_stream_key(event)].append(event)

    def build(self) -> Workload:
        all_ts = [e["ts"] for events in self.api_by_stream.values() for e in events] + [
            p["ts"] for prompts in self.prompts_by_stream.values() for p in prompts
        ]
        t0 = min(all_ts) if all_ts else 0

        turns: list[Turn] = []
        for key, api_calls in self.api_by_stream.items():
            api_calls.sort(key=lambda e: e["ts"])
            turns.extend(self._stream_turns(key, api_calls, t0))

        turns_by_stream: dict[StreamKey, list[Turn]] = defaultdict(list)
        for turn in turns:
            turns_by_stream[turn.stream].append(turn)
        for stream_turns in turns_by_stream.values():
            stream_turns.sort(key=lambda t: t.arrival_ms)

        spawned_turns = {t.stream: t for t in turns if t.spawned}
        self._reconcile_spawn_modes(turns, spawned_turns)
        return Workload(
            turns=sorted(turns, key=lambda t: t.arrival_ms),
            turns_by_stream=dict(turns_by_stream),
            spawned_turns=spawned_turns,
            t0_ms=t0,
            skipped=dict(self.skipped),
        )

    def _reconcile_spawn_modes(
        self, turns: list[Turn], spawned_turns: dict[StreamKey, Turn]
    ) -> None:
        """The trace is the ground truth for whether a parent waited on a spawn.

        Some async launches don't set ``run_in_background`` (seat agents launched
        via the Agent tool's async path): their tool_result is a millisecond ack
        while the child runs for hours. Gating the parent on such a child would
        inflate its turn by the child's whole chain — so a spawn whose traced wait
        is far shorter than its child's traced chain is reclassified background.
        """
        for turn in turns:
            for step in turn.steps:
                for tool in step.tools:
                    if tool.spawned_stream is None or tool.background:
                        continue
                    child = spawned_turns.get(tool.spawned_stream)
                    child_traced = child.traced_latency_ms if child else None
                    if child_traced is not None and (tool.duration_ms + 1_000 < child_traced):
                        tool.background = True
                        self.skipped["spawn_reclassified_background"] += 1
                    elif child_traced is not None:
                        tool.overhead_ms = max(0.0, tool.duration_ms - child_traced)

    def _steps_for(
        self, key: StreamKey, api_calls: list[dict[str, Any]], arrival_ts: int
    ) -> list[ModelStep]:
        steps = []
        prev_ready = arrival_ts  # traced moment the next request could have been issued
        for api in api_calls:
            ts = api["ts"]
            ts_last = max(api.get("ts_last") or ts, ts)  # backward ts_last is malformed
            step = ModelStep(
                step_id=api.get("uuid") or f"{key[0]}:{ts}",
                service_ms=max(float(ts_last - ts), MIN_SERVICE_MS),
                pre_gap_ms=max(float(ts - prev_ready), 0.0),
            )
            prev_ready = ts_last
            for tool in self.tools_by_api.get((key, api.get("uuid") or ""), []):
                if tool.get("ts_result") is not None and not tool.get("background"):
                    prev_ready = max(prev_ready, tool["ts_result"])
                spawned = tool.get("spawned_agent")
                spawned_key: StreamKey | None = (key[0], spawned) if spawned else None
                if spawned_key is not None and spawned_key not in self.api_by_stream:
                    # child transcript missing/empty — fall back to the traced delay
                    self.skipped["spawn_child_missing"] += 1
                    spawned_key = None
                step.tools.append(
                    ToolStep(
                        tool_id=tool["id"],
                        name=tool.get("name") or "?",
                        duration_ms=float(tool.get("duration_ms") or 0.0),
                        spawned_stream=spawned_key,
                        background=tool.get("background") is True,
                    )
                )
            steps.append(step)
        return steps

    def _traced_latency(
        self, arrival_ts: int, api_calls: list[dict[str, Any]], key: StreamKey
    ) -> float | None:
        """Observed wall-clock from arrival to the last traced activity of the chain
        (model end or sync tool result)."""
        end = arrival_ts
        for api in api_calls:
            end = max(end, api.get("ts_last") or api["ts"], api["ts"])
            for tool in self.tools_by_api.get((key, api.get("uuid") or ""), []):
                if tool.get("ts_result") is not None and not tool.get("background"):
                    end = max(end, tool["ts_result"])
        return float(end - arrival_ts) if end > arrival_ts else None

    def _stream_turns(self, key: StreamKey, api_calls: list[dict[str, Any]], t0: int) -> list[Turn]:
        """Split a stream's api timeline into turns at its prompt boundaries.

        Main streams: every non-sidechain user prompt opens a turn. Agent streams:
        the spawn opens turn 0 (the only turn the parent's sync tool waits on);
        later injected prompts (SendMessage continuations to a long-lived seat agent)
        open follow-up turns released on their own traced arrivals — without this
        split, a parent would appear to wait on the agent's whole lifetime.
        """
        is_agent = key[1] is not None
        prompts = sorted(self.prompts_by_stream.get(key, []), key=lambda p: p["ts"])
        if not is_agent:
            prompts = [p for p in prompts if not p.get("sidechain")]  # legacy echoes
            if not prompts:
                self.skipped["stream_no_prompts"] += 1
                return []
        # assign each api step to the latest prompt at or before it. Steps that
        # precede the first prompt form their own group (-1): on a main stream
        # that is resumed-session tail work, on an agent stream the spawn turn —
        # merging either with a later prompt's turn corrupts arrivals and gating.
        groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for api in api_calls:
            idx = -1
            for i, prompt in enumerate(prompts):
                if prompt["ts"] <= api["ts"]:
                    idx = i
                else:
                    break
            groups[idx].append(api)
        session = self.sessions.get(key, {})
        turns = []
        for n, (idx, apis) in enumerate(sorted(groups.items())):
            # an agent's first group is its spawn turn. If that work actually
            # follows a much later injected prompt, the parent's tiny traced wait
            # flips the spawn to background in _reconcile_spawn_modes — a sync
            # survivor means the parent demonstrably waited the whole span.
            spawned = is_agent and n == 0
            if spawned:
                spawn = self.spawn_ts.get(key) or session.get("t_start") or apis[0]["ts"]
                arrival_ts = min(spawn, apis[0]["ts"])
            elif idx < 0:  # main stream: resumed tail work before any prompt
                arrival_ts = apis[0]["ts"]
            else:
                arrival_ts = min(prompts[idx]["ts"], apis[0]["ts"])
            turns.append(
                Turn(
                    turn_id=f"{key[0]}#{key[1] or 'main'}#t{n}",
                    stream=key,
                    arrival_ms=float(arrival_ts - t0),
                    steps=self._steps_for(key, apis, arrival_ts),
                    traced_latency_ms=self._traced_latency(arrival_ts, apis, key),
                    spawned=spawned,
                    background=is_agent and session.get("background") is True,
                )
            )
        return turns


def build_workload(events_path: Path) -> Workload:
    builder = _Builder()
    builder.load(events_path)
    return builder.build()


def _replica_turn(turn: Turn, tag: str, offset_ms: float) -> Turn:
    stream = (f"{tag}:{turn.stream[0]}", turn.stream[1])
    steps = [
        replace(
            step,
            tools=[
                replace(
                    tool,
                    spawned_stream=(f"{tag}:{tool.spawned_stream[0]}", tool.spawned_stream[1])
                    if tool.spawned_stream is not None
                    else None,
                )
                for tool in step.tools
            ],
        )
        for step in turn.steps
    ]
    return replace(
        turn,
        turn_id=f"{tag}:{turn.turn_id}",
        stream=stream,
        arrival_ms=turn.arrival_ms + offset_ms,
        steps=steps,
    )


def replicate_workload(workload: Workload, factor: int) -> Workload:
    """Scale load the way a serving fleet experiences it: `factor` copies of the
    workload as independent sessions, phase-shifted by deterministic offsets drawn
    uniformly over the trace span (seeded — reruns are byte-identical). Replica 0
    is the original; time compression stays a separate, documented knob.
    """
    if factor <= 1:
        return workload
    span = max((t.arrival_ms for t in workload.clock_turns), default=0.0)
    rng = random.Random(REPLICATE_SEED)  # noqa: S311 — deterministic methodology, not crypto
    turns = list(workload.turns)
    for i in range(1, factor):
        offset = rng.uniform(0.0, span)
        turns.extend(_replica_turn(t, f"r{i}", offset) for t in workload.turns)

    turns_by_stream: dict[StreamKey, list[Turn]] = defaultdict(list)
    for turn in turns:
        turns_by_stream[turn.stream].append(turn)
    for stream_turns in turns_by_stream.values():
        stream_turns.sort(key=lambda t: t.arrival_ms)
    return Workload(
        turns=sorted(turns, key=lambda t: t.arrival_ms),
        turns_by_stream=dict(turns_by_stream),
        spawned_turns={t.stream: t for t in turns if t.spawned},
        t0_ms=workload.t0_ms,
        skipped=dict(workload.skipped),
    )
