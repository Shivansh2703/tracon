from __future__ import annotations

from agent_obs.corpus import Snapshot
from agent_obs.gate import check


def _base_snapshot(**overrides) -> Snapshot:
    defaults = {
        "label": "s",
        "corpus_id": None,
        "schema_version": 1,
        "generated_at": None,
        "sessions": 1,
        "agents": 20,
        "unaccounted": 2,
        "never_returned": 0,
        "tool_calls": 20,
        "tool_errors": 0,
        "tool_ms_total": 100.0,
        "model_ms_total": 100.0,
        "duration_p50_ms": 10.0,
        "duration_p95_ms": 1000.0,
        "duration_p99_ms": 2000.0,
        "slowest_call_ms": 2000.0,
        "longtail_share_60s": 0.0,
        "tokens": {"in": 0, "out": 0, "cache_read": 0, "cache_create": 0},
        "cache_read_share_p50": 0.5,
        "by_agent_type": {},
    }
    defaults.update(overrides)
    return Snapshot(**defaults)


def test_small_n_rise_is_noise_large_n_same_rise_is_signal() -> None:
    # Small n: 2/20 -> 3/20 — same relative rise (10% -> 15%), should NOT fire (noise).
    baseline_small = _base_snapshot(unaccounted=2, agents=20)
    current_small = _base_snapshot(unaccounted=3, agents=20)
    regressions_small = check(baseline_small, current_small)
    assert not any(r.metric == "unaccounted_rate" for r in regressions_small)

    # Large n: 200/2000 -> 300/2000 — same 10% -> 15% rise, should fire (signal).
    baseline_large = _base_snapshot(unaccounted=200, agents=2000)
    current_large = _base_snapshot(unaccounted=300, agents=2000)
    regressions_large = check(baseline_large, current_large)
    assert any(r.metric == "unaccounted_rate" for r in regressions_large)


def test_improvement_is_never_flagged() -> None:
    baseline = _base_snapshot(unaccounted=300, agents=2000)
    current = _base_snapshot(unaccounted=200, agents=2000)
    regressions = check(baseline, current)
    assert not any(r.metric == "unaccounted_rate" for r in regressions)


def test_threshold_metric_needs_both_relative_and_absolute_floor() -> None:
    # 5% relative rise on p95 (below 10% tolerance) must not fire even though it clears
    # the 1000ms floor.
    baseline = _base_snapshot(duration_p95_ms=20_000.0)
    current = _base_snapshot(duration_p95_ms=21_000.0)
    regressions = check(baseline, current, tolerance=0.10)
    assert not any(r.metric == "duration_p95_ms" for r in regressions)

    # 20% relative rise, comfortably above tolerance and floor -> fires.
    current_big = _base_snapshot(duration_p95_ms=24_000.0)
    regressions_big = check(baseline, current_big, tolerance=0.10)
    assert any(r.metric == "duration_p95_ms" for r in regressions_big)


def test_ungated_metrics_never_appear() -> None:
    baseline = _base_snapshot(tool_ms_total=10.0, model_ms_total=90.0, cache_read_share_p50=0.9)
    current = _base_snapshot(tool_ms_total=90.0, model_ms_total=10.0, cache_read_share_p50=0.1)
    regressions = check(baseline, current)
    assert not any(r.metric in ("tool_share", "cache_read_share_p50") for r in regressions)
