"""Q1 — looping and non-termination.

**The measurement problem, stated up front.** The export strips tool arguments
to a depth-1 *shape*: key names, value types, and string lengths
(``command:s78``). Two different 78-character shell commands share a shape.
So "the agent repeated the same call" is not directly observable, and this
module reports a bracket instead of pretending otherwise:

* **upper bound** — consecutive calls with the same ``(tool name, args shape)``.
  Every true repeat is in here, plus an unknown number of shape collisions.
* **lower bound** — the same, additionally requiring identical
  ``result_chars``. A repeated call that returns a byte-identical-length result
  is very unlikely to be two different commands; near-certainly a real repeat,
  but it misses real repeats whose output changed (``git status`` twice around
  an edit).

The truth is between them. Both are reported everywhere; neither is collapsed
into a single headline number.
"""

from __future__ import annotations

from collections import Counter

from ..loader import Corpus, Stream
from ..stats import quantiles, wilson

# A run this long is not "checked twice", it is a loop a human would call stuck.
STUCK_RUN_THRESHOLD = 5


def _signature(call: dict, strict: bool) -> tuple:
    if strict:
        return (call["name"], call["args_shape"], call["result_chars"])
    return (call["name"], call["args_shape"])


def consecutive_runs(stream: Stream, strict: bool = False) -> list[dict]:
    """Maximal runs of back-to-back identical-signature calls (length >= 2)."""
    calls = stream.tool_calls
    runs: list[dict] = []
    i = 0
    while i < len(calls):
        j = i
        sig = _signature(calls[i], strict)
        while j + 1 < len(calls) and _signature(calls[j + 1], strict) == sig:
            j += 1
        length = j - i + 1
        if length >= 2:
            runs.append(
                {
                    "length": length,
                    "tool": calls[i]["name"],
                    "args_shape": calls[i]["args_shape"],
                    "start_ts": calls[i].get("ts"),
                    "errors_in_run": sum(1 for c in calls[i : j + 1] if c["is_error"]),
                }
            )
        i = j + 1
    return runs


def analyze(corpus: Corpus) -> dict:
    total_calls = sum(len(s.tool_calls) for s in corpus.streams.values())
    streams_with_calls = [s for s in corpus.streams.values() if s.tool_calls]

    out: dict = {
        "total_tool_calls": total_calls,
        "streams_with_tool_calls": len(streams_with_calls),
        "stuck_run_threshold": STUCK_RUN_THRESHOLD,
    }

    for label, strict in (("upper_bound", False), ("lower_bound", True)):
        runs_by_stream = {s.key: consecutive_runs(s, strict) for s in streams_with_calls}
        all_runs = [r for runs in runs_by_stream.values() for r in runs]
        calls_in_runs = sum(r["length"] for r in all_runs)
        stuck_streams = {
            key for key, runs in runs_by_stream.items()
            if any(r["length"] >= STUCK_RUN_THRESHOLD for r in runs)
        }
        looping_streams = {key for key, runs in runs_by_stream.items() if runs}
        lengths = [r["length"] for r in all_runs]

        out[label] = {
            "runs": len(all_runs),
            "share_of_calls_inside_a_repeat_run": wilson(calls_in_runs, total_calls).as_dict(),
            "share_of_streams_with_any_repeat": wilson(
                len(looping_streams), len(streams_with_calls)
            ).as_dict(),
            "share_of_streams_with_a_stuck_run": wilson(
                len(stuck_streams), len(streams_with_calls)
            ).as_dict(),
            "run_length_distribution": dict(sorted(Counter(lengths).items())[:12]),
            "run_length_quantiles": quantiles([float(x) for x in lengths]),
            "longest_runs": sorted(all_runs, key=lambda r: -r["length"])[:5],
            "runs_by_tool": Counter(r["tool"] for r in all_runs).most_common(8),
            "errors_inside_runs": sum(r["errors_in_run"] for r in all_runs),
        }

    # Is a repeat run a *predictor* of a bad ending, or just a habit?
    # Only subagent streams carry an end status, so this is scoped to them.
    subs = [s for s in corpus.subagent_streams if s.tool_calls]
    with_stuck, with_stuck_bad, without_stuck, without_stuck_bad = 0, 0, 0, 0
    for stream in subs:
        stuck = any(r["length"] >= STUCK_RUN_THRESHOLD for r in consecutive_runs(stream))
        bad = stream.end_status in {"failed", "killed"}
        if stuck:
            with_stuck += 1
            with_stuck_bad += bad
        else:
            without_stuck += 1
            without_stuck_bad += bad
    out["stuck_run_vs_bad_ending"] = {
        "subagent_streams_scored": len(subs),
        "with_stuck_run": wilson(with_stuck_bad, with_stuck).as_dict(),
        "without_stuck_run": wilson(without_stuck_bad, without_stuck).as_dict(),
        "note": (
            "'bad ending' = end_status failed or killed. Only 25 such endings exist "
            "corpus-wide, so this comparison is underpowered by construction."
        ),
    }
    return out
