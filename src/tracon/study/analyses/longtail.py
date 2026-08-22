"""Q3 — the long tail: a few calls hold most of the wall clock. What are they?

Prior characterization of this corpus found ~3.7% of tool calls holding ~75% of
tool time. That is a scheduling fact; this module asks the reliability question
instead — are those calls *failures*, *waits on a human*, or genuine heavy work?
The three have completely different fixes, and conflating them is how "agent
reliability" work goes wrong.

Classification is by tool identity and observable structure only, never by
guessing intent:

* ``waiting_on_human`` — AskUserQuestion / ExitPlanMode. The clock is running on
  a person, not the agent. Counting these as agent latency is a measurement bug.
* ``waiting_on_agent`` — Agent / Monitor / TaskStop: the parent is blocked on a
  child run or an explicit wait.
* ``errored`` — the call ultimately failed.
* ``heavy_work`` — everything else that succeeded: builds, test suites, network.
"""

from __future__ import annotations

from collections import Counter, defaultdict

from ..loader import Corpus
from ..stats import quantiles, wilson

HUMAN_WAIT_TOOLS = {"AskUserQuestion", "ExitPlanMode"}
AGENT_WAIT_TOOLS = {"Agent", "Monitor", "TaskStop", "SendMessage"}
THRESHOLDS_MS = (10_000, 30_000, 60_000, 300_000, 600_000, 1_800_000)


def classify(call: dict) -> str:
    if call["is_error"]:
        return "errored"
    if call["name"] in HUMAN_WAIT_TOOLS:
        return "waiting_on_human"
    if call["name"] in AGENT_WAIT_TOOLS or call.get("background"):
        return "waiting_on_agent"
    return "heavy_work"


def analyze(corpus: Corpus) -> dict:
    timed = [c for c in corpus.tool_calls if c.get("duration_ms") is not None]
    total_ms = sum(c["duration_ms"] for c in timed)

    tiers = {}
    for threshold in THRESHOLDS_MS:
        above = [c for c in timed if c["duration_ms"] >= threshold]
        if not above:
            continue
        above_ms = sum(c["duration_ms"] for c in above)
        buckets = Counter(classify(c) for c in above)
        ms_by_class: dict[str, int] = defaultdict(int)
        for call in above:
            ms_by_class[classify(call)] += call["duration_ms"]
        tiers[f"ge_{threshold//1000}s"] = {
            "calls": len(above),
            "share_of_calls": wilson(len(above), len(timed)).as_dict(),
            "share_of_tool_time_pct": round(100 * above_ms / total_ms, 2) if total_ms else 0.0,
            "composition_by_calls": {
                k: wilson(v, len(above)).as_dict() for k, v in buckets.most_common()
            },
            "composition_by_time_pct": {
                k: round(100 * v / above_ms, 2) for k, v in sorted(ms_by_class.items(), key=lambda kv: -kv[1])
            },
            "by_tool": Counter(c["name"] for c in above).most_common(8),
        }

    # The extreme tail deserves individual attention: these are the hangs.
    extremes = sorted(timed, key=lambda c: -c["duration_ms"])[:15]
    return {
        "timed_calls": len(timed),
        "total_tool_hours": round(total_ms / 3_600_000, 1),
        "duration_quantiles_ms": quantiles([float(c["duration_ms"]) for c in timed]),
        "tiers": tiers,
        "extremes": [
            {
                "tool": c["name"],
                "minutes": round(c["duration_ms"] / 60_000, 1),
                "class": classify(c),
                "is_error": c["is_error"],
                "background": c.get("background"),
                "result_chars": c["result_chars"],
            }
            for c in extremes
        ],
        "never_returned": {
            "definition": "tool_use with no tool_result on disk — the stream died with the call in flight",
            "count": sum(1 for c in corpus.tool_calls if c["status"] == "unmatched"),
            "rate": wilson(
                sum(1 for c in corpus.tool_calls if c["status"] == "unmatched"),
                sum(1 for _ in corpus.tool_calls),
            ).as_dict(),
            "by_tool": Counter(
                c["name"] for c in corpus.tool_calls if c["status"] == "unmatched"
            ).most_common(6),
        },
    }
