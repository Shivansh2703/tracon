"""Q4 — do failures cluster near context limits or compaction?

This is the folk claim the study can actually test, because every tool call
joins back to the api_call that issued it, and that call reports exactly how
many input tokens the model was holding.

Two tests:
1. error rate across context-size bins, with a Cochran-Armitage trend test —
   so a flat curve is reported as flat *on evidence*, not on eyeballing;
2. error rate in the window after a compaction versus the corpus baseline.

Test 2 is underpowered in this corpus and the output says so in-band rather
than in a footnote.
"""

from __future__ import annotations

from collections import Counter

from ..loader import Corpus
from ..stats import cochran_armitage_trend, two_proportion_test, wilson

BIN_TOKENS = 25_000
MAX_BIN = 12  # 300k+ collapses into the top bin
POST_COMPACT_WINDOW_MS = 10 * 60 * 1000
MIN_BIN_CALLS = 200
STRATA_TOOLS = 3  # how many of the busiest tools to re-run the trend inside


def busiest_tools(corpus: Corpus, count: int = STRATA_TOOLS) -> list[str]:
    """The ``count`` most-used tools, which are what stratification runs inside.

    Chosen by call volume rather than named literally so the same analysis
    applies to a corpus from a different harness, whose tools are called
    something else. On the study's own corpus this returns Bash, Read, Edit —
    the three that were previously hard-coded — so no original figure moves.
    """
    counts = Counter(c["name"] for c in corpus.tool_calls if c["name"])
    return [name for name, _ in counts.most_common(count)]


def analyze(corpus: Corpus) -> dict:
    bins: dict[int, list[int]] = {}
    unjoinable = 0
    for call in corpus.tool_calls:
        tokens = corpus.context_tokens(call)
        if tokens is None:
            unjoinable += 1
            continue
        index = min(tokens // BIN_TOKENS, MAX_BIN)
        entry = bins.setdefault(index, [0, 0])
        entry[0] += 1
        entry[1] += int(call["is_error"])

    rows = []
    table = {}
    for index in sorted(bins):
        total, errs = bins[index]
        lo_k = index * BIN_TOKENS // 1000
        label = f"{lo_k:03d}k+" if index == MAX_BIN else f"{lo_k:03d}-{lo_k + BIN_TOKENS//1000:03d}k"
        table[label] = wilson(errs, total).as_dict()
        if total >= MIN_BIN_CALLS:
            rows.append((float(index), errs, total))

    trend = cochran_armitage_trend(rows)

    # Confound control. Tool mix shifts with context size — a long-running session
    # does proportionally more cheap Reads — and tools have very different error
    # rates, so an unstratified trend can be pure composition. Re-run the trend
    # inside single tools to see whether anything survives.
    stratified = {}
    for tool in busiest_tools(corpus):
        tool_bins: dict[int, list[int]] = {}
        for call in corpus.tool_calls:
            if call["name"] != tool:
                continue
            tokens = corpus.context_tokens(call)
            if tokens is None:
                continue
            index = min(tokens // BIN_TOKENS, MAX_BIN)
            entry = tool_bins.setdefault(index, [0, 0])
            entry[0] += 1
            entry[1] += int(call["is_error"])
        tool_rows = [
            (float(i), tool_bins[i][1], tool_bins[i][0])
            for i in sorted(tool_bins)
            if tool_bins[i][0] >= MIN_BIN_CALLS
        ]
        stratified[tool] = {
            "calls": sum(v[0] for v in tool_bins.values()),
            "bins_used": len(tool_rows),
            "trend_test": cochran_armitage_trend(tool_rows),
            "error_rate_by_bin": {
                f"{i*BIN_TOKENS//1000:03d}k": wilson(tool_bins[i][1], tool_bins[i][0]).as_dict()
                for i in sorted(tool_bins)
                if tool_bins[i][0] >= MIN_BIN_CALLS
            },
        }

    # Tool composition per bin, so a reader can see the confound directly.
    composition: dict[str, dict] = {}
    for index in sorted(bins):
        if bins[index][0] < MIN_BIN_CALLS:
            continue
        counts: dict[str, int] = {}
        for call in corpus.tool_calls:
            tokens = corpus.context_tokens(call)
            if tokens is None or min(tokens // BIN_TOKENS, MAX_BIN) != index:
                continue
            counts[call["name"] or "?"] = counts.get(call["name"] or "?", 0) + 1
        total = sum(counts.values())
        composition[f"{index*BIN_TOKENS//1000:03d}k"] = {
            name: round(100 * count / total, 1)
            for name, count in sorted(counts.items(), key=lambda kv: -kv[1])[:4]
        }

    # Compaction window vs baseline.
    all_calls = list(corpus.tool_calls)
    baseline_err = sum(1 for c in all_calls if c["is_error"])
    near_total = near_err = 0
    for stream in corpus.streams.values():
        if not stream.compacts:
            continue
        stamps = [c["ts"] for c in stream.compacts if c.get("ts")]
        for call in stream.tool_calls:
            ts = call.get("ts")
            if ts is None:
                continue
            if any(0 <= ts - stamp <= POST_COMPACT_WINDOW_MS for stamp in stamps):
                near_total += 1
                near_err += int(call["is_error"])

    compacts = [c for stream in corpus.streams.values() for c in stream.compacts]
    triggers: dict[str, int] = {}
    for compact in compacts:
        triggers[compact.get("trigger") or "unknown"] = triggers.get(compact.get("trigger") or "unknown", 0) + 1

    return {
        "calls_joined_to_context_size": len(all_calls) - unjoinable,
        "calls_unjoinable": unjoinable,
        "error_rate_by_context_bin": table,
        "bins_used_in_trend_test": len(rows),
        "min_calls_per_bin_for_trend": MIN_BIN_CALLS,
        "trend_test": trend,
        "trend_test_stratified_by_tool": stratified,
        "tool_composition_by_context_bin_pct": composition,
        "compaction": {
            "events": len(compacts),
            "streams_with_any_compaction": sum(1 for s in corpus.streams.values() if s.compacts),
            "by_trigger": triggers,
            "post_compaction_window_minutes": POST_COMPACT_WINDOW_MS // 60000,
            "error_rate_after_compaction": wilson(near_err, near_total).as_dict(),
            "baseline_error_rate": wilson(baseline_err, len(all_calls)).as_dict(),
            "test": two_proportion_test(near_err, near_total, baseline_err, len(all_calls)),
            "power_warning": (
                "Only %d compaction events exist corpus-wide. This comparison can rule out a "
                "large effect and nothing smaller." % len(compacts)
            ),
        },
    }
