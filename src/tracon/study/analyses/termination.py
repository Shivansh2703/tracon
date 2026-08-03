"""Q5/Q6 — how runs end, whether they recover, and the limits of asking traces
about premature confidence.

Subagent runs are the only executions in this corpus with a machine-recorded
outcome (``end_status`` from the parent's task-notification). Main sessions have
no completion record at all — a human closed them — so every rate here is scoped
to subagents and says so.

**Premature confidence is largely unanswerable from these traces**, and this
module exists partly to make that concrete rather than to work around it.
Whether an agent "decided it had enough information when it didn't" is a claim
about the content of its reasoning and the correctness of its answer. The export
holds neither. What can be measured is a shape: runs that concluded ``completed``
on very little evidence-gathering. A thin run may be a correctly small task. The
number below is an upper bound on suspicion, not a failure count.
"""

from __future__ import annotations

from collections import Counter

from ..loader import Corpus
from ..stats import quantiles, two_proportion_test, wilson

THIN_EVIDENCE_MAX_CALLS = 2


def analyze(corpus: Corpus) -> dict:
    subs = corpus.subagent_streams
    statuses = Counter(s.end_status or "unknown" for s in subs)
    total = len(subs)

    # Recovery: after a run's first error, did it go on to finish?
    with_error = [
        s for s in subs if any(c["is_error"] for c in s.tool_calls)
    ]
    recovered = sum(1 for s in with_error if s.end_status == "completed")
    clean = [s for s in subs if s.tool_calls and not any(c["is_error"] for c in s.tool_calls)]
    clean_completed = sum(1 for s in clean if s.end_status == "completed")

    # Thin-evidence proxy.
    completed = [s for s in subs if s.end_status == "completed"]
    call_counts = Counter()
    for stream in completed:
        n = len(stream.tool_calls)
        call_counts["0" if n == 0 else "1-2" if n <= 2 else "3-9" if n < 10 else "10+"] += 1
    thin = sum(1 for s in completed if len(s.tool_calls) <= THIN_EVIDENCE_MAX_CALLS)

    return {
        "subagent_runs": total,
        "end_status_counts": dict(statuses.most_common()),
        "end_status_rates": {
            status: wilson(count, total).as_dict() for status, count in statuses.most_common()
        },
        "unknown_status_note": (
            "'unknown' means the parent transcript held no terminal notification — usually a "
            "synchronous run whose result was consumed inline, or a parent that ended first. It "
            "is missing data, not a failure, and is excluded from success-rate denominators below."
        ),
        "recovery": {
            "runs_containing_at_least_one_tool_error": len(with_error),
            "error_runs_completed_rate": wilson(recovered, len(with_error)).as_dict(),
            "runs_with_no_tool_error": len(clean),
            "clean_runs_completed_rate": wilson(clean_completed, len(clean)).as_dict(),
            "test": two_proportion_test(recovered, len(with_error), clean_completed, len(clean)),
            # Confound control. 'unknown' is not a failure, it is an unobserved
            # outcome, and it is not distributed evenly: short synchronous runs
            # (which are also the ones least likely to have hit an error) often
            # have no terminal notification at all. Comparing raw completion
            # rates therefore compares observability as much as recovery. Redo
            # it among runs whose outcome was actually recorded.
            "known_status_only": {
                "note": "denominator excludes end_status 'unknown'",
                "error_runs": wilson(
                    recovered, sum(1 for s in with_error if s.end_status != "unknown")
                ).as_dict(),
                "clean_runs": wilson(
                    clean_completed, sum(1 for s in clean if s.end_status != "unknown")
                ).as_dict(),
                "test": two_proportion_test(
                    recovered, sum(1 for s in with_error if s.end_status != "unknown"),
                    clean_completed, sum(1 for s in clean if s.end_status != "unknown"),
                ),
            },
            "unknown_status_share": {
                "error_runs": wilson(
                    sum(1 for s in with_error if s.end_status == "unknown"), len(with_error)
                ).as_dict(),
                "clean_runs": wilson(
                    sum(1 for s in clean if s.end_status == "unknown"), len(clean)
                ).as_dict(),
            },
            "note": (
                "A completed status is the parent's report that the run finished, not a verdict "
                "that its work was correct. Read this as 'did the run survive', not 'did it succeed'."
            ),
        },
        "hard_failures": {
            "failed_or_killed": wilson(
                statuses.get("failed", 0) + statuses.get("killed", 0), total
            ).as_dict(),
            "by_agent_type": Counter(
                s.agent_type for s in subs if s.end_status in {"failed", "killed"}
            ).most_common(6),
        },
        "premature_confidence": {
            "answerable": False,
            "why": (
                "Requires the content of the agent's conclusion and a ground truth for whether it "
                "was right. The export strips both by design. No number in this study should be "
                "read as measuring premature confidence."
            ),
            "weak_shape_proxy": {
                "definition": f"end_status=completed with <= {THIN_EVIDENCE_MAX_CALLS} tool calls",
                "rate": wilson(thin, len(completed)).as_dict(),
                "completed_runs_by_tool_call_count": dict(call_counts.most_common()),
                "caveat": "A small task legitimately needs few calls. This bounds suspicion, not error.",
            },
        },
        "run_length": {
            "tool_calls_per_subagent_run": quantiles(
                [float(len(s.tool_calls)) for s in subs]
            ),
        },
    }
