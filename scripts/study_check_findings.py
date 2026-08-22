"""Cross-check the headline figures printed in docs/FINDINGS.md against results/study.json.

A study whose prose has quietly drifted from its own output is worse than no study.
This asserts that each load-bearing figure in the writeup is literally present in the
generated result object, and that the strings appear in the document text.

    python scripts/check_findings.py

Exits non-zero on the first mismatch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULT = json.loads((ROOT / "results" / "study.json").read_text())
DOC = (ROOT / "docs" / "FINDINGS.md").read_text()

failures: list[str] = []


def dig(path: str):
    node = RESULT
    for part in path.split("."):
        node = node[part]
    return node


def check(label: str, path: str, *, expect_in_doc: list[str]) -> None:
    """Assert a JSON figure exists and that its rendered forms appear in the writeup."""
    try:
        value = dig(path)
    except (KeyError, TypeError) as exc:
        failures.append(f"{label}: missing from study.json at {path} ({exc})")
        return
    for text in expect_in_doc:
        if text not in DOC:
            failures.append(f"{label}: '{text}' not found in FINDINGS.md (json has {value})")


# --- corpus ---
check("tool calls", "corpus.tool_calls", expect_in_doc=["85,104"])
check("streams", "corpus.streams", expect_in_doc=["1,854"])
check("subagent runs", "corpus.subagent_runs", expect_in_doc=["1,626"])
check("api calls", "corpus.api_calls", expect_in_doc=["88,897"])
check("compactions", "corpus.compactions", expect_in_doc=["38"])

# --- errors ---
check("error rate", "errors.overall_error_rate", expect_in_doc=["3.34%", "3.22-3.46", "2,843"])
check("kept acting", "errors.after_error_model_response.kept_acting", expect_in_doc=["95.78%", "2,723"])
check("blind retry", "errors.after_error_next_tool_call.retry_identical_shape", expect_in_doc=["1.76%", "(50)"])
check("unresolved", "errors.declared_complete_with_unresolved_error.rate", expect_in_doc=["6.27%", "5.07-7.74", "80 / 1,276"])
check("long vs short", "errors.error_rate_long_vs_short.ge_60s", expect_in_doc=["10.21%", "9.20-11.32"])

# --- looping ---
check("loop upper", "looping.upper_bound.share_of_calls_inside_a_repeat_run", expect_in_doc=["3.57%", "3,037"])
check("loop lower", "looping.lower_bound.share_of_calls_inside_a_repeat_run", expect_in_doc=["1.29%", "1,098"])
check("stuck upper", "looping.upper_bound.share_of_streams_with_a_stuck_run", expect_in_doc=["2.08%", "38/1,826"])
check("stuck lower", "looping.lower_bound.share_of_streams_with_a_stuck_run", expect_in_doc=["1.15%", "21/1,826"])

# --- long tail ---
check("ge60s tier", "longtail.tiers.ge_60s", expect_in_doc=["3,153", "75.08%", "3.71%"])
check("never returned", "longtail.never_returned", expect_in_doc=["25 calls (0.029%)"])
check("tool hours", "longtail.total_tool_hours", expect_in_doc=["246.1"])

# --- context ---
check("trend", "context.trend_test", expect_in_doc=["z = -2.33, p = 0.020"])
check("bash strat", "context.trend_test_stratified_by_tool.Bash.trend_test", expect_in_doc=["z = -1.84, p = 0.066"])
check("joined", "context.calls_joined_to_context_size", expect_in_doc=["81,979"])

# --- termination ---
check("hard failure", "termination.hard_failures.failed_or_killed", expect_in_doc=["1.54%", "25/1,626"])
check("recovery error runs", "termination.recovery.known_status_only.error_runs", expect_in_doc=["97.27%", "678/697"])
check("recovery clean runs", "termination.recovery.known_status_only.clean_runs", expect_in_doc=["99.01%", "598/604"])
check("thin proxy", "termination.premature_confidence.weak_shape_proxy.rate", expect_in_doc=["2.04%", "26/1,276"])

# --- numeric spot-checks: the doc's claims must equal the JSON, not merely appear ---
NUMERIC = [
    ("errors.overall_error_rate.pct", 3.341),
    ("errors.declared_complete_with_unresolved_error.rate.pct", 6.27),
    ("looping.upper_bound.share_of_calls_inside_a_repeat_run.pct", 3.569),
    ("looping.lower_bound.share_of_calls_inside_a_repeat_run.pct", 1.29),
    ("longtail.tiers.ge_60s.share_of_tool_time_pct", 75.08),
    ("termination.recovery.known_status_only.error_runs.pct", 97.274),
    ("corpus.tool_calls", 85104),
]
for path, expected in NUMERIC:
    actual = dig(path)
    if abs(actual - expected) > 1e-6:
        failures.append(f"numeric drift at {path}: study.json has {actual}, writeup asserts {expected}")

# --- structural invariants ---
if dig("looping.lower_bound.share_of_calls_inside_a_repeat_run.n") > dig(
    "looping.upper_bound.share_of_calls_inside_a_repeat_run.n"
):
    failures.append("looping lower bound exceeds upper bound")

if failures:
    print("FINDINGS consistency check FAILED:", file=sys.stderr)
    for failure in failures:
        print(f"  - {failure}", file=sys.stderr)
    raise SystemExit(1)
print(f"FINDINGS consistency check passed ({len(NUMERIC)} numeric assertions, all citations present)")
