"""Workload characterization over exported trace events.

Reads an export directory (``events.jsonl`` + ``manifest.json``) and computes the
distributions the scheduler work is built on: arrival patterns, tool-call latency
share, dependency/parallelism structure, and session/context reuse. Emits
``stats.json`` (exact numbers) and ``report.md`` (readable tables). Every number is
computed from the events on disk — nothing asserted, nothing sampled.
"""

from __future__ import annotations

import itertools
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

LONG_CALL_THRESHOLDS_MS = (10_000, 30_000, 60_000)
TOP_TOOLS = 12
PARALLEL_FANOUT_MIN = 2
_MS_PER_S = 1_000
_MS_PER_MIN = 60_000


def _quantile(sorted_values: list[float], q: float) -> float:
    """Nearest-rank quantile on a pre-sorted list."""
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, math.ceil(q * len(sorted_values)) - 1))
    return sorted_values[idx]


def dist(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    n = len(ordered)
    return {
        "n": n,
        "mean": round(sum(ordered) / n, 2) if n else 0.0,
        "p50": _quantile(ordered, 0.50),
        "p90": _quantile(ordered, 0.90),
        "p95": _quantile(ordered, 0.95),
        "p99": _quantile(ordered, 0.99),
        "max": ordered[-1] if n else 0.0,
    }


class Characterizer:
    def __init__(self, traces_dir: Path) -> None:
        self._dir = traces_dir
        self._events_path = traces_dir / "events.jsonl"

        # accumulators, filled by one streaming pass
        self._main_sessions: list[dict[str, Any]] = []
        self._agent_sessions: list[dict[str, Any]] = []
        self._prompts_by_session: dict[str, list[int]] = defaultdict(list)
        self._queue_ops: Counter[str] = Counter()
        self._tool_durations: list[float] = []
        self._tool_time_by_name: Counter[str] = Counter()
        self._tool_count_by_name: Counter[str] = Counter()
        self._tool_durations_by_name: dict[str, list[float]] = defaultdict(list)
        self._n_tool_errors = 0
        self._n_tool_background = 0
        self._n_tool_matched = 0
        self._n_tool_unmatched = 0
        self._n_tool_orphan = 0
        self._streams: dict[tuple[str, str | None], list[tuple[int, int]]] = defaultdict(list)
        self._fanout: list[float] = []
        self._api_spans_ms: list[float] = []
        self._api_models: Counter[str] = Counter()
        self._tokens = Counter()
        self._cache_ratios: list[float] = []
        self._turn_durations: list[float] = []
        self._turn_pending_bg: list[float] = []
        self._n_compacts = 0
        self._agent_end: dict[tuple[str, str], int] = {}
        self._notifications: list[dict[str, Any]] = []

    # -- pass --

    def run(self) -> dict[str, Any]:
        with self._events_path.open(encoding="utf-8") as fh:
            for raw in fh:
                event = json.loads(raw)
                getattr(self, f"_on_{event['ev']}", self._on_ignored)(event)
        manifest = self._load_manifest()
        return {
            "corpus": self._corpus_stats(manifest),
            "arrivals": self._arrival_stats(),
            "tool_latency": self._tool_stats(),
            "structure": self._structure_stats(),
            "context": self._context_stats(),
        }

    def _load_manifest(self) -> dict[str, Any]:
        path = self._dir / "manifest.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def _on_ignored(self, _event: dict[str, Any]) -> None:
        pass

    def _on_session(self, event: dict[str, Any]) -> None:
        if event["agent"] is None:
            self._main_sessions.append(event)
        else:
            self._agent_sessions.append(event)
            if event.get("t_end") is not None:
                self._agent_end[(event["session"], event["agent"])] = event["t_end"]

    def _on_prompt(self, event: dict[str, Any]) -> None:
        if event["agent"] is None and not event.get("sidechain"):
            self._prompts_by_session[event["session"]].append(event["ts"])

    def _on_queue_op(self, event: dict[str, Any]) -> None:
        self._queue_ops[event.get("op") or "?"] += 1

    def _on_tool_call(self, event: dict[str, Any]) -> None:
        status = event.get("status")
        if status == "unmatched":
            self._n_tool_unmatched += 1
            return
        if status == "orphan_result":
            self._n_tool_orphan += 1
            return
        self._n_tool_matched += 1
        if event.get("is_error"):
            self._n_tool_errors += 1
        if event.get("background"):
            self._n_tool_background += 1
        duration = event.get("duration_ms")
        if duration is None or duration < 0:
            return
        name = event.get("name") or "?"
        self._tool_durations.append(duration)
        self._tool_time_by_name[name] += duration
        self._tool_count_by_name[name] += 1
        self._tool_durations_by_name[name].append(duration)
        if event.get("ts") is not None and event.get("ts_result") is not None:
            self._streams[(event["session"], event["agent"])].append(
                (event["ts"], event["ts_result"])
            )

    def _on_api_call(self, event: dict[str, Any]) -> None:
        blocks = event.get("blocks") or {}
        self._fanout.append(blocks.get("tool_use") or 0)
        if event.get("model"):
            self._api_models[event["model"]] += 1
        ts, ts_last = event.get("ts"), event.get("ts_last")
        if ts is not None and ts_last is not None and ts_last >= ts:
            self._api_spans_ms.append(ts_last - ts)
        usage = event.get("usage") or {}
        for key in ("in", "out", "cache_read", "cache_create"):
            value = usage.get(key)
            if isinstance(value, (int, float)):
                self._tokens[key] += value
        read = usage.get("cache_read") or 0
        total_input = (usage.get("in") or 0) + read + (usage.get("cache_create") or 0)
        if total_input > 0:
            self._cache_ratios.append(read / total_input)

    def _on_turn(self, event: dict[str, Any]) -> None:
        if event.get("duration_ms") is not None:
            self._turn_durations.append(event["duration_ms"])
        # the raw field is written only when >0 (null means none pending)
        pending = event.get("pending_background_agents")
        self._turn_pending_bg.append(pending if isinstance(pending, (int, float)) else 0)

    def _on_compact(self, _event: dict[str, Any]) -> None:
        self._n_compacts += 1

    def _on_notification(self, event: dict[str, Any]) -> None:
        self._notifications.append(event)

    # -- stats blocks --

    def _corpus_stats(self, manifest: dict[str, Any]) -> dict[str, Any]:
        starts = [s["t_start"] for s in self._main_sessions if s.get("t_start") is not None]
        ends = [s["t_end"] for s in self._main_sessions if s.get("t_end") is not None]
        wall_ms = [
            s["t_end"] - s["t_start"]
            for s in self._main_sessions
            if s.get("t_start") is not None and s.get("t_end") is not None
        ]
        return {
            "sessions": len(self._main_sessions),
            "agents": len(self._agent_sessions),
            "span_days": round((max(ends) - min(starts)) / 86_400_000, 1) if starts else 0,
            "session_hours_total": round(sum(wall_ms) / 3_600_000, 1),
            "session_wall_minutes": dist([w / 60_000 for w in wall_ms]),
            "models": dict(self._api_models.most_common()),
            "claude_code_versions": len(manifest.get("versions_seen", [])),
            "source_lines": sum(manifest.get("lines_by_type", {}).values()),
        }

    def _arrival_stats(self) -> dict[str, Any]:
        per_session = [len(v) for v in self._prompts_by_session.values()]
        inter_arrival_s: list[float] = []
        for times in self._prompts_by_session.values():
            ordered = sorted(times)
            inter_arrival_s.extend((b - a) / 1000 for a, b in itertools.pairwise(ordered) if b > a)
        n_prompts = sum(per_session)
        delivered = self._queue_ops.get("dequeue", 0)
        return {
            "prompts": n_prompts,
            "prompts_per_session": dist([float(x) for x in per_session]),
            "inter_arrival_s": dist(inter_arrival_s),
            "queue_ops": dict(self._queue_ops.most_common()),
            "queue_delivered_share": round(delivered / n_prompts, 3) if n_prompts else 0,
        }

    def _tool_stats(self) -> dict[str, Any]:
        total_time = sum(self._tool_durations)
        by_tool = {}
        for name, count in self._tool_count_by_name.most_common(TOP_TOOLS):
            durations = self._tool_durations_by_name[name]
            by_tool[name] = {
                "n": count,
                "p50_ms": _quantile(sorted(durations), 0.5),
                "p95_ms": _quantile(sorted(durations), 0.95),
                "time_share": round(self._tool_time_by_name[name] / total_time, 3)
                if total_time
                else 0,
            }
        long_calls = {}
        for threshold in LONG_CALL_THRESHOLDS_MS:
            over = [d for d in self._tool_durations if d >= threshold]
            long_calls[f"over_{threshold // 1000}s"] = {
                "call_share": round(len(over) / len(self._tool_durations), 4)
                if self._tool_durations
                else 0,
                "time_share": round(sum(over) / total_time, 4) if total_time else 0,
            }
        model_time = sum(self._api_spans_ms)
        busy = model_time + total_time
        return {
            "calls_matched": self._n_tool_matched,
            "calls_unmatched": self._n_tool_unmatched,
            "calls_orphan": self._n_tool_orphan,
            "duration_ms": dist(self._tool_durations),
            "total_hours": round(total_time / 3_600_000, 1),
            "error_rate": round(self._n_tool_errors / self._n_tool_matched, 4)
            if self._n_tool_matched
            else 0,
            "background_share": round(self._n_tool_background / self._n_tool_matched, 4)
            if self._n_tool_matched
            else 0,
            "by_tool": by_tool,
            "long_calls": long_calls,
            "model_hours_total": round(model_time / 3_600_000, 1),
            "tool_share_of_busy_time": round(total_time / busy, 3) if busy else 0,
        }

    def _structure_stats(self) -> dict[str, Any]:
        fanout_counts = Counter(int(f) for f in self._fanout)
        n_api = len(self._fanout)
        with_tools = sum(c for f, c in fanout_counts.items() if f >= 1)
        parallel_api = sum(c for f, c in fanout_counts.items() if f >= PARALLEL_FANOUT_MIN)

        agents_per_session = Counter(a["session"] for a in self._agent_sessions)
        spawn_depths = Counter(
            a.get("spawn_depth") for a in self._agent_sessions if a.get("spawn_depth") is not None
        )
        end_statuses = Counter(a.get("end_status") or "unknown" for a in self._agent_sessions)
        n_background = sum(1 for a in self._agent_sessions if a.get("background"))
        agent_runtime_min = [
            (a["t_end"] - a["t_start"]) / 60_000
            for a in self._agent_sessions
            if a.get("t_start") is not None and a.get("t_end") is not None
        ]

        overlapped = 0
        total_streamed = 0
        for calls in self._streams.values():
            calls.sort()
            max_end = None
            for ts, ts_end in calls:
                total_streamed += 1
                if max_end is not None and ts < max_end:
                    overlapped += 1
                max_end = ts_end if max_end is None else max(max_end, ts_end)

        lags_s = []
        for notif in self._notifications:
            agent_ref = notif.get("agent_ref")
            if not isinstance(agent_ref, str):
                continue
            agent_end = self._agent_end.get((notif["session"], agent_ref))
            if agent_end is not None and notif.get("ts") is not None and notif["ts"] >= agent_end:
                lags_s.append((notif["ts"] - agent_end) / 1000)

        return {
            "api_calls": n_api,
            "api_calls_with_tools_share": round(with_tools / n_api, 3) if n_api else 0,
            "parallel_fanout_share": round(parallel_api / with_tools, 3) if with_tools else 0,
            "fanout_max": max(fanout_counts) if fanout_counts else 0,
            "sessions_with_agents": len(agents_per_session),
            "agents_per_spawning_session": dist([float(c) for c in agents_per_session.values()]),
            "spawn_depth": {str(k): v for k, v in sorted(spawn_depths.items())},
            "agent_end_status": dict(end_statuses.most_common()),
            "background_agent_share": round(n_background / len(self._agent_sessions), 3)
            if self._agent_sessions
            else 0,
            "agent_runtime_minutes": dist(agent_runtime_min),
            "tool_parallel_overlap_share": round(overlapped / total_streamed, 3)
            if total_streamed
            else 0,
            "notification_lag_s": dist(lags_s),
        }

    def _context_stats(self) -> dict[str, Any]:
        return {
            "tokens_total": {k: int(v) for k, v in self._tokens.items()},
            "cache_read_ratio": dist([round(r, 4) for r in self._cache_ratios]),
            "turns": len(self._turn_durations),
            "turn_duration_s": dist([d / 1000 for d in self._turn_durations]),
            "turns_with_pending_background_share": round(
                sum(1 for p in self._turn_pending_bg if p > 0) / len(self._turn_pending_bg), 3
            )
            if self._turn_pending_bg
            else 0,
            "compactions": self._n_compacts,
        }


# -- report rendering --


def _fmt_ms(ms: float) -> str:
    if ms >= _MS_PER_MIN:
        return f"{ms / _MS_PER_MIN:.1f}m"
    if ms >= _MS_PER_S:
        return f"{ms / _MS_PER_S:.1f}s"
    return f"{ms:.0f}ms"


def _dist_row(label: str, d: dict[str, float], fmt=lambda v: f"{v:,.1f}") -> str:
    return (
        f"| {label} | {d['n']:,} | {fmt(d['p50'])} | {fmt(d['p90'])} "
        f"| {fmt(d['p95'])} | {fmt(d['p99'])} | {fmt(d['max'])} |"
    )


def render_report(stats: dict[str, Any]) -> str:
    corpus = stats["corpus"]
    arrivals = stats["arrivals"]
    tools = stats["tool_latency"]
    structure = stats["structure"]
    context = stats["context"]

    lines = [
        "# Workload characterization",
        "",
        (
            f"{corpus['sessions']} main sessions and {corpus['agents']} subagent runs over "
            f"{corpus['span_days']} days of real multi-agent coding work; "
            f"{corpus['session_hours_total']:,} session-hours, "
            f"{corpus['source_lines']:,} raw transcript lines, "
            f"{corpus['claude_code_versions']} Claude Code versions."
        ),
        "",
        "## Arrivals",
        "",
        (
            f"- {arrivals['prompts']:,} human prompt arrivals; per-session p50 "
            f"{arrivals['prompts_per_session']['p50']:.0f}, max "
            f"{arrivals['prompts_per_session']['max']:.0f}"
        ),
        (
            f"- inter-arrival within a session: p50 {arrivals['inter_arrival_s']['p50']:,.0f}s, "
            f"p95 {arrivals['inter_arrival_s']['p95']:,.0f}s"
        ),
        (
            f"- queue activity {arrivals['queue_ops']}: "
            f"{arrivals['queue_delivered_share']:.0%} of prompts were delivered from the "
            "queue (typed while the agent was still working) rather than at an idle prompt"
        ),
        "",
        "## Tool-call latency",
        "",
        "| | n | p50 | p90 | p95 | p99 | max |",
        "|---|---|---|---|---|---|---|",
        _dist_row("all tool calls", tools["duration_ms"], _fmt_ms),
        "",
        (
            f"- tool execution accounts for **{tools['total_hours']:,} hours** vs "
            f"{tools['model_hours_total']:,} model-streaming hours: "
            f"**{tools['tool_share_of_busy_time']:.0%} of busy time is tools**"
        ),
        (
            f"- error rate {tools['error_rate']:.1%}; "
            f"background launches {tools['background_share']:.1%}"
        ),
        "",
        "### The long tail",
        "",
        "| threshold | share of calls | share of tool time |",
        "|---|---|---|",
    ]
    for name, row in tools["long_calls"].items():
        threshold = name.removeprefix("over_")
        lines.append(f"| ≥{threshold} | {row['call_share']:.2%} | {row['time_share']:.2%} |")
    lines += [
        "",
        "### By tool",
        "",
        "| tool | n | p50 | p95 | share of tool time |",
        "|---|---|---|---|---|",
    ]
    for name, row in tools["by_tool"].items():
        lines.append(
            f"| {name} | {row['n']:,} | {_fmt_ms(row['p50_ms'])} "
            f"| {_fmt_ms(row['p95_ms'])} | {row['time_share']:.1%} |"
        )
    lines += [
        "",
        "## Dependency structure",
        "",
        (
            f"- {structure['api_calls']:,} model calls; "
            f"{structure['api_calls_with_tools_share']:.0%} issue tools; of those, "
            f"{structure['parallel_fanout_share']:.0%} issue ≥2 in parallel "
            f"(max fan-out {structure['fanout_max']})"
        ),
        (
            f"- {structure['tool_parallel_overlap_share']:.0%} of tool calls overlap another "
            "call in the same stream — the rest are strictly sequential chain links"
        ),
        (
            f"- {structure['sessions_with_agents']} sessions spawn subagents "
            f"(per-spawner p50 {structure['agents_per_spawning_session']['p50']:.0f}, "
            f"max {structure['agents_per_spawning_session']['max']:.0f}); "
            f"spawn depth distribution {structure['spawn_depth']}"
        ),
        (
            f"- agent end status: {structure['agent_end_status']}; "
            f"{structure['background_agent_share']:.0%} run in background"
        ),
        (
            f"- agent runtime: p50 {structure['agent_runtime_minutes']['p50']:.1f}m, "
            f"p95 {structure['agent_runtime_minutes']['p95']:.1f}m, "
            f"max {structure['agent_runtime_minutes']['max']:.0f}m"
        ),
        (
            f"- parent idle-wait after a background agent finishes (notification lag): "
            f"p50 {structure['notification_lag_s']['p50']:,.0f}s, "
            f"p95 {structure['notification_lag_s']['p95']:,.0f}s"
        ),
        "",
        "## Session / context reuse",
        "",
        f"- tokens: {context['tokens_total']}",
        (
            f"- cache-read share of input: p50 {context['cache_read_ratio']['p50']:.1%} "
            f"(mean {context['cache_read_ratio']['mean']:.1%}) — context warmth is the "
            "common case, cold context the exception"
        ),
        (
            f"- {context['turns']:,} turns; duration "
            f"p50 {context['turn_duration_s']['p50']:,.0f}s, "
            f"p95 {context['turn_duration_s']['p95']:,.0f}s; "
            f"{context['turns_with_pending_background_share']:.0%} of turns end with background "
            f"agents still running; {context['compactions']} context compactions"
        ),
        "",
    ]
    return "\n".join(lines) + "\n"


def characterize(traces_dir: Path, out_dir: Path | None = None) -> dict[str, Any]:
    out = out_dir if out_dir is not None else traces_dir
    stats = Characterizer(traces_dir).run()
    out.mkdir(parents=True, exist_ok=True)
    (out / "stats.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(render_report(stats), encoding="utf-8")
    return stats
