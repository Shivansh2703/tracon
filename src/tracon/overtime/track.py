"""Turn N snapshots into a fleet-over-time timeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from agent_obs.corpus import Snapshot

# key, display name, unit, higher_is_worse
_WATCHED: tuple[tuple[str, str, str, bool], ...] = (
    ("unaccounted_rate", "Unaccounted rate (raw)", "pct", True),
    ("unaccounted_resolvable_rate", "Unaccounted rate (resolvable only)", "pct", True),
    ("never_returned_rate", "Never-returned rate", "pct", True),
    ("tool_error_rate", "Tool error rate", "pct", True),
    ("longtail_share_60s", "Long-tail share (>=60s)", "pct", True),
    ("duration_p95_ms", "Tool duration p95", "ms", True),
    ("duration_p99_ms", "Tool duration p99", "ms", True),
    ("tool_share", "Tool-time share", "pct", None),
    ("cache_read_share_p50", "Cache-read share (median)", "pct", None),
)

# A metric moved "meaningfully" for the narrative section if it cleared this floor.
_MOVE_FLOOR = {
    "pct": 0.01,
    "ms": 1000.0,
}

_MIN_SNAPSHOTS_FOR_DELTA = 2


def _sort_key(snapshot: Snapshot, order: int) -> tuple[bool, datetime | float, int]:
    if snapshot.generated_at:
        try:
            parsed = datetime.fromisoformat(snapshot.generated_at)
        except ValueError:
            return (True, 0.0, order)
        return (False, parsed, order)
    return (True, 0.0, order)


def build_timeline(snapshots: list[Snapshot]) -> dict:
    ordered = [s for _, s in sorted(
        ((_sort_key(s, i), s) for i, s in enumerate(snapshots)),
        key=lambda pair: pair[0],
    )]

    labels = [s.label for s in ordered]
    metrics: dict[str, Any] = {}
    for key, name, unit, higher_is_worse in _WATCHED:
        values = [getattr(s, key) for s in ordered]
        entry = {
            "display_name": name,
            "unit": unit,
            "higher_is_worse": higher_is_worse,
            "values": values,
        }
        if len(values) >= _MIN_SNAPSHOTS_FOR_DELTA:
            entry["delta_first_to_last"] = _delta(values[0], values[-1])
            entry["delta_prev_to_last"] = _delta(values[-2], values[-1])
        else:
            entry["delta_first_to_last"] = None
            entry["delta_prev_to_last"] = None
        metrics[key] = entry

    last = ordered[-1] if ordered else None
    by_agent_type = {}
    if last is not None:
        by_agent_type = {k: v.to_dict() for k, v in last.by_agent_type.items()}

    return {
        "labels": labels,
        "metrics": metrics,
        "single_snapshot": len(ordered) < _MIN_SNAPSHOTS_FOR_DELTA,
        "last_by_agent_type": by_agent_type,
        "last_unresolvable": last.unresolvable if last is not None else 0,
    }


def _delta(a: float | None, b: float | None) -> float | None:
    return b - a if a is not None and b is not None else None


def _fmt(value: float | None, unit: str) -> str:
    if value is None:
        return "n/a"
    if unit == "pct":
        return f"{100 * value:.2f}%"
    return f"{value:.0f}ms"


def _render_table(labels: list[str], metrics: dict[str, Any]) -> list[str]:
    header = "| Metric | " + " | ".join(labels) + " |"
    sep = "|---" * (len(labels) + 1) + "|"
    lines = [header, sep]
    for key, _name, _unit, _higher in _WATCHED:
        entry = metrics[key]
        row = [entry["display_name"]]
        row.extend(_fmt(v, entry["unit"]) for v in entry["values"])
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    return lines


def _what_moved(metrics: dict[str, Any]) -> list[str]:
    moved: list[str] = []
    for key, _name, unit, higher_is_worse in _WATCHED:
        entry = metrics[key]
        delta = entry["delta_first_to_last"]
        if delta is None:
            continue
        floor = _MOVE_FLOOR[unit]
        if abs(delta) < floor:
            continue
        direction = "up" if delta > 0 else "down"
        verdict = ""
        if higher_is_worse is True:
            verdict = " (worse)" if delta > 0 else " (better)"
        elif higher_is_worse is False:
            verdict = " (not gated — direction is not obviously bad)"
        moved.append(f"- {entry['display_name']}: {direction} {_fmt(abs(delta), unit)}{verdict}")

    lines = ["## What moved"]
    lines.extend(moved or ["- Nothing moved past the reporting floor."])
    lines.append("")
    return lines


def _render_by_agent_type(by_type: dict[str, dict]) -> list[str]:
    lines = [
        "## By agent type (last snapshot)",
        (
            "Agent type names are user-chosen strings from the local fleet config — they stay "
            "on this machine and never leave this report."
        ),
    ]
    if not by_type:
        lines.append("(no subagent runs in the last snapshot)")
        lines.append("")
        return lines

    ranked = sorted(by_type.items(), key=lambda kv: kv[1]["unaccounted"], reverse=True)
    lines.append(
        "| Agent type | Runs | Unaccounted | Unresolvable | Rate (resolvable) | Tool minutes |"
    )
    lines.append("|---|---|---|---|---|---|")
    for name, stats in ranked:
        resolvable = stats["resolvable_runs"]
        resolvable_unaccounted = stats["unaccounted_resolvable"]
        rate_str = (
            f"{100 * resolvable_unaccounted / resolvable:.2f}%" if resolvable else "n/a"
        )
        tool_min = stats["tool_ms"] / 60_000
        lines.append(
            f"| {name} | {stats['runs']} | {stats['unaccounted']} | {stats['unresolvable']} | "
            f"{rate_str} | {tool_min:.1f} |"
        )
    lines.append("")
    return lines


def _render_unresolvable_caveat(unresolvable: int) -> list[str]:
    if unresolvable <= 0:
        return []
    return [
        (
            "Some subagent runs' outcomes cannot be recovered from this export at all — the "
            "data needed to resolve them was never captured, regardless of how those runs "
            "actually ended. They are counted in the raw rate above and excluded from the "
            "resolvable-only rate. Their presence is a property of how traces are captured, "
            "not a fleet problem."
        ),
        "",
    ]


def render_timeline(timeline: dict) -> str:
    labels: list[str] = timeline["labels"]
    metrics: dict[str, Any] = timeline["metrics"]
    lines: list[str] = ["# Fleet timeline\n"]

    if timeline["single_snapshot"]:
        lines.append(
            "Only one snapshot supplied — no deltas to report; add more to see movement.\n"
        )

    lines.extend(_render_table(labels, metrics))
    lines.extend(_render_unresolvable_caveat(timeline.get("last_unresolvable", 0)))
    lines.extend(_what_moved(metrics))
    lines.extend(_render_by_agent_type(timeline["last_by_agent_type"]))

    return "\n".join(lines)
