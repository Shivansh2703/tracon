"""CI-style regression gate: compare a baseline snapshot against a current one."""

from __future__ import annotations

from dataclasses import dataclass

from agent_obs.corpus import Snapshot
from agent_obs.stats import two_proportion_test, wilson

# metric key -> (numerator attr, denominator attr)
_PROPORTION_METRICS = {
    "unaccounted_rate": ("unaccounted", "agents"),
    "never_returned_rate": ("never_returned", "tool_calls"),
    "tool_error_rate": ("tool_errors", "tool_calls"),
}

# metric key -> (display name, absolute-change floor)
_THRESHOLD_METRICS = {
    "duration_p95_ms": ("Tool duration p95", 1000.0),
    "duration_p99_ms": ("Tool duration p99", 1000.0),
    "longtail_share_60s": ("Long-tail share (>=60s)", 0.01),
}

_DISPLAY_NAMES = {
    "unaccounted_rate": "Unaccounted rate",
    "never_returned_rate": "Never-returned rate",
    "tool_error_rate": "Tool error rate",
}

# Reported but never gated — direction is not obviously bad.
_UNGATED_METRICS = ("tool_share", "cache_read_share_p50")

_SIGNIFICANCE_P = 0.05


@dataclass
class Regression:
    metric: str
    display_name: str
    baseline_value: float
    current_value: float
    rule: str
    evidence: dict


def check(baseline: Snapshot, current: Snapshot, tolerance: float = 0.10) -> list[Regression]:
    regressions: list[Regression] = []

    for metric, (num_attr, den_attr) in _PROPORTION_METRICS.items():
        base_num, base_den = getattr(baseline, num_attr), getattr(baseline, den_attr)
        cur_num, cur_den = getattr(current, num_attr), getattr(current, den_attr)
        base_rate = base_num / base_den if base_den else 0.0
        cur_rate = cur_num / cur_den if cur_den else 0.0
        if cur_rate <= base_rate:
            continue
        test = two_proportion_test(cur_num, cur_den, base_num, base_den)
        if test["p"] >= _SIGNIFICANCE_P:
            continue
        regressions.append(
            Regression(
                metric=metric,
                display_name=_DISPLAY_NAMES[metric],
                baseline_value=base_rate,
                current_value=cur_rate,
                rule="proportion-test",
                evidence={
                    "p": test["p"],
                    "baseline_ci95_pct": wilson(base_num, base_den).as_dict()["ci95_pct"],
                    "current_ci95_pct": wilson(cur_num, cur_den).as_dict()["ci95_pct"],
                },
            )
        )

    for metric, (display_name, floor) in _THRESHOLD_METRICS.items():
        base_value = getattr(baseline, metric)
        cur_value = getattr(current, metric)
        change = cur_value - base_value
        if cur_value <= base_value * (1 + tolerance):
            continue
        if abs(change) < floor:
            continue
        regressions.append(
            Regression(
                metric=metric,
                display_name=display_name,
                baseline_value=base_value,
                current_value=cur_value,
                rule="threshold",
                evidence={
                    "relative_change": change / base_value if base_value else float("inf"),
                    "absolute_change": change,
                    "tolerance": tolerance,
                    "floor": floor,
                },
            )
        )

    return regressions


def render_check(regressions: list[Regression], baseline: Snapshot, current: Snapshot) -> str:
    lines = [f"# Regression check: {baseline.label} -> {current.label}\n"]

    if not regressions:
        lines.append("No regressions found.\n")
    else:
        lines.append(f"{len(regressions)} regression(s) found:\n")
        for r in regressions:
            lines.append(f"## {r.display_name} ({r.rule})")
            lines.append(f"- baseline: {r.baseline_value:.4g}")
            lines.append(f"- current:  {r.current_value:.4g}")
            if r.rule == "proportion-test":
                lines.append(
                    f"- two-proportion test p = {r.evidence['p']:.4g} "
                    "(a rise is only reported here when the test rules out sampling noise)"
                )
                lines.append(f"- baseline Wilson 95% CI: {r.evidence['baseline_ci95_pct']}")
                lines.append(f"- current Wilson 95% CI: {r.evidence['current_ci95_pct']}")
            else:
                lines.append(
                    f"- relative change {r.evidence['relative_change']:.2%} exceeds tolerance "
                    f"{r.evidence['tolerance']:.0%}, absolute change "
                    f"{r.evidence['absolute_change']:.4g} clears the {r.evidence['floor']:.4g} "
                    "floor (threshold comparison, not a statistical test — this metric has no n)"
                )
            lines.append("")

    lines.append(
        "Not gated (reported only — direction is not obviously bad): "
        + ", ".join(_UNGATED_METRICS)
    )
    lines.append("")
    return "\n".join(lines)
