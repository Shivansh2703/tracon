"""``tracon doctor`` — what went wrong in your agent runs, and what it cost.

Reads a trace export and reports the things that are invisible while you work: runs that
ended with no recorded outcome, tool calls that never returned, the long tail that holds
most of your wall-clock, and the shape of your token spend.

Everything is computed locally from your own transcripts. Nothing is uploaded, and no
content ever enters this module — it reads the normalized export, which is content-free
by construction (see ``tracon.trace.privacy``).

On the reference numbers below: they are measured, cited, and drawn from a **single
operator's** corpus. They are a point of comparison, not a norm. An honest reading of one
machine's numbers is that they describe that machine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Terminal statuses that mean a run genuinely finished. Anything else — including a
# missing status — is unaccounted: not success, not failure, just no record.
ACCOUNTED = frozenset({"completed", "failed"})

LONG_TAIL_THRESHOLDS_MS = (10_000, 30_000, 60_000)

# Measured on the reference corpus, 2026-08-14: 202 sessions / 1,239 subagent runs over
# 22.7 days, one operator, one machine, an agent-heavy workflow. The first two replicated
# to the digit against an independent export whose transcripts do not overlap. The third
# did not replicate anywhere, because no public corpus is both multi-agent and untruncated
# — it is shown for comparison and explicitly not as a norm.
REFERENCE = {
    "tool_share_of_busy_time": (0.79, "replicated on an independent corpus"),
    "cache_read_share_p50": (0.991, "replicated on an independent corpus"),
    "unaccounted_run_rate": (0.165, "ONE machine only — never validated elsewhere"),
}


def _q(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round(p * (len(ordered) - 1)))
    return ordered[idx]


@dataclass
class Findings:
    sessions: int = 0
    agents: int = 0
    unaccounted: int = 0
    unaccounted_examples: list[dict] = field(default_factory=list)
    never_returned: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    tool_ms_total: float = 0.0
    model_ms_total: float = 0.0
    durations_ms: list[float] = field(default_factory=list)
    by_tool_ms: dict[str, float] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)
    cache_shares: list[float] = field(default_factory=list)

    @property
    def unaccounted_rate(self) -> float:
        return self.unaccounted / self.agents if self.agents else 0.0

    @property
    def tool_share(self) -> float:
        busy = self.tool_ms_total + self.model_ms_total
        return self.tool_ms_total / busy if busy else 0.0


def _ingest_session(f: Findings, d: dict) -> None:
    if d.get("agent") is None:
        f.sessions += 1
        return
    f.agents += 1
    status = d.get("end_status")
    if status in ACCOUNTED:
        return
    f.unaccounted += 1
    t0, t1 = d.get("t_start"), d.get("t_end")
    f.unaccounted_examples.append(
        {
            "agent": d.get("agent"),
            "agent_type": d.get("agent_type"),
            "status": status,
            "runtime_min": (t1 - t0) / 60000.0 if _both_numeric(t0, t1) else None,
            "background": d.get("background"),
        }
    )


def _ingest_tool(f: Findings, d: dict) -> None:
    f.tool_calls += 1
    if d.get("status") != "matched":
        f.never_returned += 1
    if d.get("is_error"):
        f.tool_errors += 1
    ms = d.get("duration_ms")
    if not isinstance(ms, (int, float)):
        return
    f.durations_ms.append(float(ms))
    f.tool_ms_total += float(ms)
    name = d.get("name") or "?"
    f.by_tool_ms[name] = f.by_tool_ms.get(name, 0.0) + float(ms)


def _ingest_api(f: Findings, d: dict, tokens: dict[str, int]) -> None:
    usage = d.get("usage") or {}
    for key in tokens:
        val = usage.get(key)
        if isinstance(val, int):
            tokens[key] += val
    read = usage.get("cache_read") or 0
    total_in = read + (usage.get("cache_create") or 0) + (usage.get("in") or 0)
    if total_in:
        f.cache_shares.append(read / total_in)
    ts, ts_last = d.get("ts"), d.get("ts_last")
    if _both_numeric(ts, ts_last):
        f.model_ms_total += max(0.0, ts_last - ts)


def diagnose(traces: Path) -> Findings:
    """Compute findings from an export directory containing ``events.jsonl``."""
    events_path = Path(traces) / "events.jsonl"
    if not events_path.exists():
        raise FileNotFoundError(f"no events.jsonl in {traces} — run `tracon export` first")

    f = Findings()
    tokens = {"in": 0, "out": 0, "cache_read": 0, "cache_create": 0}
    handlers = {
        "session": lambda d: _ingest_session(f, d),
        "tool_call": lambda d: _ingest_tool(f, d),
        "api_call": lambda d: _ingest_api(f, d, tokens),
    }

    with events_path.open(errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            handler = handlers.get(d.get("ev"))
            if handler is not None:
                handler(d)

    f.tokens = tokens
    f.unaccounted_examples.sort(key=lambda e: e["runtime_min"] or 0.0, reverse=True)
    return f


def _both_numeric(a: object, b: object) -> bool:
    return isinstance(a, (int, float)) and isinstance(b, (int, float))


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def _mins(ms: float) -> str:
    return f"{ms / 60000.0:.1f} min"


def render(f: Findings) -> str:
    """Human-readable report. Leads with what is wrong, not with what is fine."""
    out: list[str] = []
    add = out.append

    add(f"tracon doctor — {f.sessions} sessions, {f.agents} agent runs\n")

    # --- the findings that are actually actionable -------------------------------
    add("## Runs that ended with no recorded outcome\n")
    if not f.agents:
        add("No subagent runs in this corpus — nothing to check.\n")
    else:
        ref, ref_note = REFERENCE["unaccounted_run_rate"]
        add(
            f"**{f.unaccounted} of {f.agents} ({_pct(f.unaccounted_rate)})** finished without "
            "recording success or failure. Not errors — no outcome at all.\n"
        )
        add(f"Reference corpus: {_pct(ref)} — {ref_note}.\n")
        if f.unaccounted_examples:
            add("Longest-running of them:\n")
            for e in f.unaccounted_examples[:5]:
                runtime = f"{e['runtime_min']:.0f} min" if e["runtime_min"] else "unknown"
                kind = e["agent_type"] or "agent"
                bg = ", background" if e["background"] else ""
                add(f"  - {kind} — ran {runtime}{bg}")
            add("")

    add("## Tool calls that never returned\n")
    add(
        f"**{f.never_returned} of {f.tool_calls}** "
        f"({_pct(f.never_returned / f.tool_calls if f.tool_calls else 0)}). "
        f"Error rate {_pct(f.tool_errors / f.tool_calls if f.tool_calls else 0)}.\n"
    )

    # --- where the time went ------------------------------------------------------
    add("## Where the time went\n")
    ref, ref_note = REFERENCE["tool_share_of_busy_time"]
    add(
        f"Tool execution is **{_pct(f.tool_share)}** of busy time "
        f"({_mins(f.tool_ms_total)} of tools vs {_mins(f.model_ms_total)} of model).\n"
    )
    add(f"Reference corpus: {_pct(ref)} — {ref_note}.\n")

    if f.durations_ms:
        total = sum(f.durations_ms)
        add("The long tail:\n")
        add("| slower than | share of calls | share of tool time |")
        add("|---|---|---|")
        for thr in LONG_TAIL_THRESHOLDS_MS:
            over = [d for d in f.durations_ms if d >= thr]
            share_time = sum(over) / total if total else 0
            add(
                f"| {thr // 1000}s | {_pct(len(over) / len(f.durations_ms))} "
                f"| {_pct(share_time)} |"
            )
        add("")
        add(
            f"Slowest single call: **{_mins(max(f.durations_ms))}**. "
            f"p50 {_q(f.durations_ms, 0.5) / 1000:.1f}s, "
            f"p95 {_q(f.durations_ms, 0.95) / 1000:.1f}s.\n"
        )

    if f.by_tool_ms:
        add("Biggest time sinks:\n")
        ranked = sorted(f.by_tool_ms.items(), key=lambda kv: kv[1], reverse=True)[:5]
        for name, ms in ranked:
            share = ms / f.tool_ms_total if f.tool_ms_total else 0
            add(f"  - {name}: {_mins(ms)} ({_pct(share)} of tool time)")
        add("")

    # --- what it cost -------------------------------------------------------------
    add("## What it cost\n")
    t = f.tokens
    add(
        f"cache-read {t['cache_read']:,} · cache-write {t['cache_create']:,} · "
        f"output {t['out']:,} · raw input {t['in']:,}\n"
    )
    if f.cache_shares:
        ref, ref_note = REFERENCE["cache_read_share_p50"]
        add(
            f"Median call reads **{_pct(_q(f.cache_shares, 0.5))}** of its input from cache "
            f"(reference: {_pct(ref)} — {ref_note}).\n"
        )
    if t["cache_read"] and t["in"]:
        add(
            f"Cache reads outnumber raw input tokens **{t['cache_read'] // t['in']:,}:1** — "
            "your bill is context rehydration, not generation.\n"
        )

    add("---")
    add(
        "Reference figures come from one operator's machine. They are a comparison, not a "
        "norm — a rate that differs from them is a difference, not a fault."
    )
    return "\n".join(out)


def to_json(f: Findings) -> dict:
    """Machine-readable findings. Same numbers as the report, nothing extra."""
    return {
        "sessions": f.sessions,
        "agents": f.agents,
        "unaccounted": f.unaccounted,
        "unaccounted_rate": round(f.unaccounted_rate, 4),
        "never_returned": f.never_returned,
        "tool_calls": f.tool_calls,
        "tool_error_rate": round(f.tool_errors / f.tool_calls, 4) if f.tool_calls else 0.0,
        "tool_share_of_busy_time": round(f.tool_share, 4),
        "tool_ms_total": round(f.tool_ms_total),
        "model_ms_total": round(f.model_ms_total),
        "slowest_call_ms": round(max(f.durations_ms)) if f.durations_ms else 0,
        "duration_p50_ms": round(_q(f.durations_ms, 0.5)),
        "duration_p95_ms": round(_q(f.durations_ms, 0.95)),
        "cache_read_share_p50": round(_q(f.cache_shares, 0.5), 4),
        "tokens": f.tokens,
        "by_tool_ms": {k: round(v) for k, v in f.by_tool_ms.items()},
    }
