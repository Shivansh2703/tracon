"""Q2 — how often tool calls fail, and what the agent does next.

The hiring-market question is the third branch: does the agent **proceed on a
failed result**? Traces cannot show that directly — content is stripped, so
whether the model's next sentence acknowledged the error is invisible. What is
observable is the *structure* of the next action, and one honest proxy for
proceeding-regardless: an agent that reported ``completed`` while its trace
still contained an error it never demonstrably resolved.

Both are reported as what they are: structure, and a proxy.
"""

from __future__ import annotations

from collections import Counter

from tracon.study.loader import Corpus
from tracon.study.stats import two_proportion_test, wilson

# An error "looks resolved" if the same tool later succeeds in the same stream.
# Crude: a later successful Bash call is not necessarily the same command
# retried. It is the strongest resolution test the stripped schema supports,
# and it is deliberately generous — so the unresolved count is a floor.


def analyze(corpus: Corpus) -> dict:
    calls = list(corpus.tool_calls)
    errors = [c for c in calls if c["is_error"]]

    by_tool = {}
    for tool, total in Counter(c["name"] for c in calls).most_common(14):
        if tool is None:
            continue
        errs = sum(1 for c in calls if c["name"] == tool and c["is_error"])
        by_tool[tool] = wilson(errs, total).as_dict()

    # --- what the model does structurally after an error ---
    next_tool = Counter()
    next_model_action = Counter()
    for stream in corpus.streams.values():
        tools = stream.tool_calls
        apis = stream.api_calls
        for idx, call in enumerate(tools):
            if not call["is_error"]:
                continue
            # (a) next tool call in the stream
            if idx + 1 >= len(tools):
                next_tool["no_further_tool_call"] += 1
            else:
                nxt = tools[idx + 1]
                if nxt["name"] == call["name"] and nxt["args_shape"] == call["args_shape"]:
                    next_tool["retry_identical_shape"] += 1
                elif nxt["name"] == call["name"]:
                    next_tool["same_tool_different_arguments"] += 1
                else:
                    next_tool["switched_tool"] += 1
            # (b) the model response that consumed the failed result
            result_ts = call.get("ts_result")
            if result_ts is None:
                next_model_action["no_result_timestamp"] += 1
                continue
            following = next((a for a in apis if a["ts"] >= result_ts), None)
            if following is None:
                next_model_action["no_further_model_call"] += 1
            elif (following.get("blocks") or {}).get("tool_use", 0) > 0:
                next_model_action["kept_acting"] += 1
            else:
                next_model_action["text_only_response"] += 1

    n_err = len(errors)
    out = {
        "overall_error_rate": wilson(n_err, len(calls)).as_dict(),
        "error_rate_by_tool": by_tool,
        "after_error_next_tool_call": {
            k: wilson(v, n_err).as_dict() for k, v in next_tool.most_common()
        },
        "after_error_model_response": {
            k: wilson(v, n_err).as_dict() for k, v in next_model_action.most_common()
        },
    }

    # --- proxy for "proceeded on a failed result" ---
    subs = [s for s in corpus.subagent_streams if s.tool_calls]
    unresolved_by_status = Counter()
    status_totals = Counter()
    last_call_errored = Counter()
    for stream in subs:
        status = stream.end_status or "unknown"
        status_totals[status] += 1
        if stream.tool_calls[-1]["is_error"]:
            last_call_errored[status] += 1
        for idx, call in enumerate(stream.tool_calls):
            if call["is_error"] and not any(
                later["name"] == call["name"] and not later["is_error"]
                for later in stream.tool_calls[idx + 1 :]
            ):
                unresolved_by_status[status] += 1
                break

    completed = status_totals.get("completed", 0)
    out["declared_complete_with_unresolved_error"] = {
        "definition": (
            "subagent whose end_status is 'completed' and whose trace contains at least one "
            "errored tool call never followed by a success of the same tool in that stream"
        ),
        "rate": wilson(unresolved_by_status.get("completed", 0), completed).as_dict(),
        "final_call_errored_rate": wilson(
            last_call_errored.get("completed", 0), completed
        ).as_dict(),
        "by_end_status": {
            status: wilson(unresolved_by_status.get(status, 0), total).as_dict()
            for status, total in status_totals.most_common()
        },
        "caveat": (
            "This is a proxy, not an observation of the agent ignoring an error. A same-tool "
            "success elsewhere in the stream is counted as resolution, which over-forgives; and "
            "an unresolved error may have been correctly reported as a limitation in the agent's "
            "final message, which the stripped trace cannot show."
        ),
    }

    # Are long calls more error-prone than short ones? (feeds the long-tail question)
    timed = [c for c in calls if c.get("duration_ms") is not None]
    long_calls = [c for c in timed if c["duration_ms"] >= 60_000]
    short_calls = [c for c in timed if c["duration_ms"] < 60_000]
    out["error_rate_long_vs_short"] = {
        "ge_60s": wilson(sum(1 for c in long_calls if c["is_error"]), len(long_calls)).as_dict(),
        "lt_60s": wilson(sum(1 for c in short_calls if c["is_error"]), len(short_calls)).as_dict(),
        "test": two_proportion_test(
            sum(1 for c in long_calls if c["is_error"]),
            len(long_calls),
            sum(1 for c in short_calls if c["is_error"]),
            len(short_calls),
        ),
    }
    return out
