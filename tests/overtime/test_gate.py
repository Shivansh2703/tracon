from __future__ import annotations

import json

from agent_obs.corpus import Snapshot
from agent_obs.gate import check, render_check


def _base_snapshot(**overrides) -> Snapshot:
    defaults = {
        "label": "s",
        "corpus_id": None,
        "schema_version": 1,
        "generated_at": None,
        "sessions": 1,
        "agents": 20,
        "unaccounted": 2,
        "unresolvable": 0,
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
    # resolvable_agents/unaccounted_resolvable are now counted directly rather than derived —
    # tests that only set agents/unaccounted/unresolvable still want the consistent (non-buggy)
    # values; a test can still pass either field explicitly to build an inconsistent fixture
    # on purpose (e.g. the malformed/adversarial-gate tests below).
    defaults.setdefault("resolvable_agents", defaults["agents"] - defaults["unresolvable"])
    defaults.setdefault(
        "unaccounted_resolvable", defaults["unaccounted"] - defaults["unresolvable"]
    )
    return Snapshot(**defaults)


def test_small_n_rise_is_noise_large_n_same_rise_is_signal() -> None:
    # Small n: 2/20 -> 3/20 — same relative rise (10% -> 15%), should NOT fire (noise).
    baseline_small = _base_snapshot(unaccounted=2, agents=20)
    current_small = _base_snapshot(unaccounted=3, agents=20)
    regressions_small = check(baseline_small, current_small)
    assert not any(r.metric == "unaccounted_resolvable_rate" for r in regressions_small)

    # Large n: 200/2000 -> 300/2000 — same 10% -> 15% rise, should fire (signal).
    baseline_large = _base_snapshot(unaccounted=200, agents=2000)
    current_large = _base_snapshot(unaccounted=300, agents=2000)
    regressions_large = check(baseline_large, current_large)
    assert any(r.metric == "unaccounted_resolvable_rate" for r in regressions_large)


def test_improvement_is_never_flagged() -> None:
    baseline = _base_snapshot(unaccounted=300, agents=2000)
    current = _base_snapshot(unaccounted=200, agents=2000)
    regressions = check(baseline, current)
    assert not any(r.metric == "unaccounted_resolvable_rate" for r in regressions)


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


def test_gate_uses_resolvable_rate_not_raw() -> None:
    # All the added "unaccounted" runs are unresolvable (workflow-only) — the resolvable rate
    # doesn't move at all, so this must NOT fire even though the raw rate rises a lot.
    baseline = _base_snapshot(unaccounted=200, unresolvable=0, agents=2000)
    current = _base_snapshot(unaccounted=400, unresolvable=200, agents=2200)
    regressions = check(baseline, current)
    assert not any(r.metric == "unaccounted_resolvable_rate" for r in regressions)


def test_gate_verdict_stable_across_round_trip() -> None:
    baseline = _base_snapshot(unaccounted=200, agents=2000)
    current = _base_snapshot(unaccounted=300, agents=2000)
    direct_verdict = bool(check(baseline, current))

    round_tripped = Snapshot.from_dict(json.loads(json.dumps(current.to_dict())))
    round_trip_verdict = bool(check(baseline, round_tripped))

    assert direct_verdict == round_trip_verdict is True


def test_gate_survives_negative_numerator_without_crashing() -> None:
    # Simulates a hand-edited/malformed baseline JSON where unaccounted_resolvable ended up
    # negative (exactly the shape the subtraction bug used to produce), with current's rate
    # "higher" than baseline's (-0.5 > -1.0) so the direction guard doesn't filter it out and
    # the gate proceeds toward the statistics. Before the fix, that fed a negative numerator
    # into two_proportion_test and raised ValueError: math domain error.
    baseline = _base_snapshot(
        agents=2, unaccounted=0, unresolvable=0, resolvable_agents=2, unaccounted_resolvable=-2
    )
    current = _base_snapshot(
        agents=2, unaccounted=0, unresolvable=0, resolvable_agents=2, unaccounted_resolvable=-1
    )
    regressions = check(baseline, current)  # must not raise
    exit_code = 1 if regressions else 0
    assert exit_code in (0, 1)
    assert not any(r.metric == "unaccounted_resolvable_rate" for r in regressions)
    assert any("Unaccounted rate (resolvable only)" in msg for msg in regressions.skipped)
    rendered = render_check(regressions, baseline, current)
    assert "Skipped Unaccounted rate (resolvable only)" in rendered
    assert "-50" not in rendered
    assert "-0.5" not in rendered


def test_malformed_baseline_skips_metric_with_message_not_crash() -> None:
    # numerator > denominator — impossible, must be skipped, not fed to the proportion test.
    baseline = _base_snapshot(
        agents=20, unaccounted=2, resolvable_agents=5, unaccounted_resolvable=999
    )
    current = _base_snapshot(agents=20, unaccounted=2)
    regressions = check(baseline, current)
    assert not any(r.metric == "unaccounted_resolvable_rate" for r in regressions)
    rendered = render_check(regressions, baseline, current)
    assert "Skipped Unaccounted rate (resolvable only)" in rendered


def test_zero_resolvable_runs_skips_metric_as_undefined() -> None:
    # Every agent is unresolvable on one side -> resolvable_agents is 0 -> rate is None
    # (nothing to compare), not zero.
    baseline = _base_snapshot(
        agents=5, unaccounted=1, unresolvable=5, resolvable_agents=0, unaccounted_resolvable=0
    )
    current = _base_snapshot(agents=5, unaccounted=3, unresolvable=0)
    assert baseline.unaccounted_resolvable_rate is None
    regressions = check(baseline, current)
    assert not any(r.metric == "unaccounted_resolvable_rate" for r in regressions)
    assert any("no resolvable runs to compare" in msg for msg in regressions.skipped)
