"""Read one trace export directory into a content-free ``Snapshot``.

An export directory holds ``manifest.json`` plus a streamed ``events.jsonl``. This module never
holds a field that could carry a path, a prompt, a branch name, a repo name, or a tool argument —
only counts, rates, and durations survive the read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ACCOUNTED = {"completed", "failed"}
_LONGTAIL_FLOOR_MS = 60_000
_UNTYPED = "(untyped)"


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _count(d: dict, key: str) -> int:
    """A field read as a non-negative, non-bool int — this package's own ``to_dict`` never
    emits anything else, so anything short of that means the JSON was hand-edited or corrupt."""
    val = d[key]
    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
        raise ValueError(f"{key!r}: expected a non-negative int, got {val!r}")
    return val


def _sub_count(d: dict, key: str, total_key: str, total: int) -> int:
    val = _count(d, key)
    if val > total:
        raise ValueError(f"{key!r} ({val}) exceeds {total_key!r} ({total})")
    return val


def _quantile(values: list[float], p: float) -> float:
    """Quantile, pinned verbatim to tracon doctor's ``_q`` (src/tracon/doctor.py:57).

    Not the nearest-rank definition agentfail's ``stats.quantiles()`` uses (``ceil(q*n)-1``) —
    doctor and agent-obs report on the same corpora side by side, so they must agree on p95 to
    the last digit or the suite quietly contradicts itself.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round(p * (len(ordered) - 1)))
    return ordered[idx]


@dataclass
class AgentTypeStats:
    runs: int = 0
    unaccounted: int = 0
    unresolvable: int = 0
    # Counted directly while streaming (see _Accumulator.add_session) rather than derived by
    # subtraction from `runs`/`unaccounted` — a subtraction is only valid if every unresolvable
    # run is also unaccounted, and nothing enforced that. Counting directly makes the impossible
    # (negative) value unconstructable instead of just clamped away.
    resolvable_runs: int = 0
    unaccounted_resolvable: int = 0
    tool_ms: float = 0.0
    runtime_ms: float = 0.0

    @property
    def unaccounted_rate(self) -> float:
        return self.unaccounted / self.runs if self.runs else 0.0

    @property
    def unaccounted_resolvable_rate(self) -> float | None:
        """None (render as n/a) when every run in this row is unresolvable."""
        return (
            self.unaccounted_resolvable / self.resolvable_runs if self.resolvable_runs else None
        )

    def to_dict(self) -> dict:
        return {
            "runs": self.runs,
            "unaccounted": self.unaccounted,
            "unresolvable": self.unresolvable,
            "resolvable_runs": self.resolvable_runs,
            "unaccounted_resolvable": self.unaccounted_resolvable,
            "tool_ms": self.tool_ms,
            "runtime_ms": self.runtime_ms,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AgentTypeStats:
        runs = _count(d, "runs")
        unaccounted = _sub_count(d, "unaccounted", "runs", runs)
        unresolvable = _sub_count(d, "unresolvable", "runs", runs)
        resolvable_runs = _sub_count(d, "resolvable_runs", "runs", runs)
        unaccounted_resolvable = _sub_count(
            d, "unaccounted_resolvable", "resolvable_runs", resolvable_runs
        )
        return cls(
            runs=runs,
            unaccounted=unaccounted,
            unresolvable=unresolvable,
            resolvable_runs=resolvable_runs,
            unaccounted_resolvable=unaccounted_resolvable,
            tool_ms=d["tool_ms"],
            runtime_ms=d["runtime_ms"],
        )


@dataclass
class Snapshot:
    label: str
    corpus_id: str | None
    schema_version: int | None
    generated_at: str | None
    sessions: int
    agents: int
    unaccounted: int
    never_returned: int
    tool_calls: int
    tool_errors: int
    tool_ms_total: float
    model_ms_total: float
    duration_p50_ms: float
    duration_p95_ms: float
    duration_p99_ms: float
    slowest_call_ms: float
    longtail_share_60s: float
    tokens: dict[str, int]
    cache_read_share_p50: float
    unresolvable: int = 0
    # Counted directly while streaming — see AgentTypeStats above for why this isn't
    # `agents - unresolvable` / `unaccounted - unresolvable`.
    resolvable_agents: int = 0
    unaccounted_resolvable: int = 0
    by_agent_type: dict[str, AgentTypeStats] = field(default_factory=dict)

    @property
    def unaccounted_rate(self) -> float:
        return self.unaccounted / self.agents if self.agents else 0.0

    @property
    def unaccounted_resolvable_rate(self) -> float | None:
        """None (render as n/a) when there are no resolvable agents to rate — same contract as
        AgentTypeStats.unaccounted_resolvable_rate."""
        return (
            self.unaccounted_resolvable / self.resolvable_agents
            if self.resolvable_agents
            else None
        )

    @property
    def never_returned_rate(self) -> float:
        return self.never_returned / self.tool_calls if self.tool_calls else 0.0

    @property
    def tool_error_rate(self) -> float:
        return self.tool_errors / self.tool_calls if self.tool_calls else 0.0

    @property
    def tool_share(self) -> float:
        total = self.tool_ms_total + self.model_ms_total
        return self.tool_ms_total / total if total else 0.0

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "corpus_id": self.corpus_id,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "sessions": self.sessions,
            "agents": self.agents,
            "unaccounted": self.unaccounted,
            "never_returned": self.never_returned,
            "tool_calls": self.tool_calls,
            "tool_errors": self.tool_errors,
            "tool_ms_total": self.tool_ms_total,
            "model_ms_total": self.model_ms_total,
            "duration_p50_ms": self.duration_p50_ms,
            "duration_p95_ms": self.duration_p95_ms,
            "duration_p99_ms": self.duration_p99_ms,
            "slowest_call_ms": self.slowest_call_ms,
            "longtail_share_60s": self.longtail_share_60s,
            "tokens": self.tokens,
            "cache_read_share_p50": self.cache_read_share_p50,
            "unresolvable": self.unresolvable,
            "resolvable_agents": self.resolvable_agents,
            "unaccounted_resolvable": self.unaccounted_resolvable,
            "by_agent_type": {k: v.to_dict() for k, v in self.by_agent_type.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> Snapshot:
        agents = _count(d, "agents")
        unaccounted = _sub_count(d, "unaccounted", "agents", agents)
        unresolvable = _sub_count(d, "unresolvable", "agents", agents)
        resolvable_agents = _sub_count(d, "resolvable_agents", "agents", agents)
        unaccounted_resolvable = _sub_count(
            d, "unaccounted_resolvable", "resolvable_agents", resolvable_agents
        )
        return cls(
            label=d["label"],
            corpus_id=d["corpus_id"],
            schema_version=d["schema_version"],
            generated_at=d["generated_at"],
            sessions=d["sessions"],
            agents=agents,
            unaccounted=unaccounted,
            never_returned=d["never_returned"],
            tool_calls=d["tool_calls"],
            tool_errors=d["tool_errors"],
            tool_ms_total=d["tool_ms_total"],
            model_ms_total=d["model_ms_total"],
            duration_p50_ms=d["duration_p50_ms"],
            duration_p95_ms=d["duration_p95_ms"],
            duration_p99_ms=d["duration_p99_ms"],
            slowest_call_ms=d["slowest_call_ms"],
            longtail_share_60s=d["longtail_share_60s"],
            tokens=d["tokens"],
            cache_read_share_p50=d["cache_read_share_p50"],
            unresolvable=unresolvable,
            resolvable_agents=resolvable_agents,
            unaccounted_resolvable=unaccounted_resolvable,
            by_agent_type={k: AgentTypeStats.from_dict(v) for k, v in d["by_agent_type"].items()},
        )


@dataclass
class _Accumulator:
    """Mutable running totals for one streamed pass over ``events.jsonl``."""

    sessions: int = 0
    agents: int = 0
    unaccounted: int = 0
    unresolvable: int = 0
    resolvable_agents: int = 0
    unaccounted_resolvable: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    never_returned: int = 0
    tool_ms_total: float = 0.0
    model_ms_total: float = 0.0
    durations: list[float] = field(default_factory=list)
    longtail_ms: float = 0.0
    tokens: dict[str, int] = field(
        default_factory=lambda: {"in": 0, "out": 0, "cache_read": 0, "cache_create": 0}
    )
    cache_read_shares: list[float] = field(default_factory=list)
    by_type: dict[str, AgentTypeStats] = field(default_factory=dict)
    agent_id_to_type: dict[str, str] = field(default_factory=dict)
    tool_ms_by_agent: dict[str, float] = field(default_factory=dict)

    def add_session(self, ev: dict) -> None:
        agent_id = ev.get("agent")
        if agent_id is None:
            self.sessions += 1
            return
        self.agents += 1
        is_unaccounted = ev.get("end_status") not in _ACCOUNTED
        if is_unaccounted:
            self.unaccounted += 1
        # A non-null `workflow` id means this run's outcome can never be resolved from this
        # export by construction — it stays counted in `unaccounted` above (unchanged
        # definition, matches tracon doctor) but is tracked separately here so a resolvable-only
        # rate can be reported alongside it. The id value itself is never stored — null/non-null
        # is the only thing tested.
        is_unresolvable = ev.get("workflow") is not None
        if is_unresolvable:
            self.unresolvable += 1
        else:
            self.resolvable_agents += 1
            if is_unaccounted:
                self.unaccounted_resolvable += 1
        agent_type = ev.get("agent_type") or _UNTYPED
        self.agent_id_to_type[agent_id] = agent_type
        stats = self.by_type.setdefault(agent_type, AgentTypeStats())
        stats.runs += 1
        if is_unaccounted:
            stats.unaccounted += 1
        if is_unresolvable:
            stats.unresolvable += 1
        else:
            stats.resolvable_runs += 1
            if is_unaccounted:
                stats.unaccounted_resolvable += 1
        t_start, t_end = ev.get("t_start"), ev.get("t_end")
        if _is_number(t_start) and _is_number(t_end):
            stats.runtime_ms += t_end - t_start

    def add_tool_call(self, ev: dict) -> None:
        self.tool_calls += 1
        if ev.get("status") != "matched":
            self.never_returned += 1
        if ev.get("is_error"):
            self.tool_errors += 1
        duration_ms = ev.get("duration_ms")
        if not _is_number(duration_ms):
            return
        self.tool_ms_total += duration_ms
        self.durations.append(float(duration_ms))
        if duration_ms >= _LONGTAIL_FLOOR_MS:
            self.longtail_ms += duration_ms
        call_agent = ev.get("agent")
        if call_agent is not None:
            self.tool_ms_by_agent[call_agent] = (
                self.tool_ms_by_agent.get(call_agent, 0.0) + duration_ms
            )

    def add_api_call(self, ev: dict) -> None:
        ts, ts_last = ev.get("ts"), ev.get("ts_last")
        if _is_number(ts) and _is_number(ts_last):
            self.model_ms_total += max(0.0, ts_last - ts)
        usage = ev.get("usage") or {}
        for key in self.tokens:
            val = usage.get(key)
            if _is_number(val):
                self.tokens[key] += val
        cache_read, cache_create, in_tok = (
            usage.get("cache_read"),
            usage.get("cache_create"),
            usage.get("in"),
        )
        if _is_number(cache_read) and _is_number(cache_create) and _is_number(in_tok):
            denom = cache_read + cache_create + in_tok
            if denom > 0:
                self.cache_read_shares.append(cache_read / denom)

    def finalize_agent_type_tool_ms(self) -> None:
        for agent_id, agent_type in self.agent_id_to_type.items():
            self.by_type[agent_type].tool_ms += self.tool_ms_by_agent.get(agent_id, 0.0)


def _read_manifest(path: Path) -> dict:
    manifest_path = path / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _stream_events(events_path: Path) -> _Accumulator:
    acc = _Accumulator()
    handlers = {
        "session": acc.add_session,
        "tool_call": acc.add_tool_call,
        "api_call": acc.add_api_call,
    }
    with events_path.open() as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if not stripped:
                continue
            try:
                ev = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            handler = handlers.get(ev.get("ev"))
            if handler is not None:
                handler(ev)
    acc.finalize_agent_type_tool_ms()
    return acc


def read_snapshot(path: str | Path) -> Snapshot:
    path = Path(path)
    events_path = path / "events.jsonl"
    if not events_path.exists():
        raise FileNotFoundError(f"{path} has no events.jsonl — not an export directory")

    manifest = _read_manifest(path)
    corpus_id = manifest.get("corpus_id")
    schema_version = manifest.get("schema_version")
    generated_at = manifest.get("generated_at")
    label = corpus_id or path.name

    acc = _stream_events(events_path)

    if acc.durations:
        p50 = _quantile(acc.durations, 0.5)
        p95 = _quantile(acc.durations, 0.95)
        p99 = _quantile(acc.durations, 0.99)
        slowest = max(acc.durations)
        longtail_share = acc.longtail_ms / acc.tool_ms_total if acc.tool_ms_total else 0.0
    else:
        p50 = p95 = p99 = slowest = 0.0
        longtail_share = 0.0

    cache_read_share_p50 = _quantile(acc.cache_read_shares, 0.5) if acc.cache_read_shares else 0.0

    return Snapshot(
        label=label,
        corpus_id=corpus_id,
        schema_version=schema_version,
        generated_at=generated_at,
        sessions=acc.sessions,
        agents=acc.agents,
        unaccounted=acc.unaccounted,
        unresolvable=acc.unresolvable,
        resolvable_agents=acc.resolvable_agents,
        unaccounted_resolvable=acc.unaccounted_resolvable,
        never_returned=acc.never_returned,
        tool_calls=acc.tool_calls,
        tool_errors=acc.tool_errors,
        tool_ms_total=acc.tool_ms_total,
        model_ms_total=acc.model_ms_total,
        duration_p50_ms=p50,
        duration_p95_ms=p95,
        duration_p99_ms=p99,
        slowest_call_ms=slowest,
        longtail_share_60s=longtail_share,
        tokens=acc.tokens,
        cache_read_share_p50=cache_read_share_p50,
        by_agent_type=acc.by_type,
    )
