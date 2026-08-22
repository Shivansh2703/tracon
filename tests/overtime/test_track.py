from __future__ import annotations

import pytest

from agent_obs.corpus import AgentTypeStats, Snapshot
from agent_obs.track import build_timeline, render_timeline


def _snap(
    label: str, generated_at: str | None, unaccounted_rate_inputs: tuple[int, int]
) -> Snapshot:
    unaccounted, agents = unaccounted_rate_inputs
    return Snapshot(
        label=label,
        corpus_id=None,
        schema_version=1,
        generated_at=generated_at,
        sessions=1,
        agents=agents,
        unaccounted=unaccounted,
        never_returned=0,
        tool_calls=10,
        tool_errors=0,
        tool_ms_total=100.0,
        model_ms_total=100.0,
        duration_p50_ms=10.0,
        duration_p95_ms=20.0,
        duration_p99_ms=30.0,
        slowest_call_ms=30.0,
        longtail_share_60s=0.0,
        tokens={"in": 0, "out": 0, "cache_read": 0, "cache_create": 0},
        cache_read_share_p50=0.5,
        by_agent_type={"sonnet-med": AgentTypeStats(runs=agents, unaccounted=unaccounted)},
    )


def test_timeline_sorts_by_generated_at_not_argument_order() -> None:
    later = _snap("later", "2026-08-14T00:00:00-04:00", (1, 10))
    earlier = _snap("earlier", "2026-07-30T00:00:00-04:00", (2, 10))
    timeline = build_timeline([later, earlier])
    assert timeline["labels"] == ["earlier", "later"]


def test_single_snapshot_is_legal_and_says_so() -> None:
    snap = _snap("only", "2026-08-14T00:00:00-04:00", (1, 10))
    timeline = build_timeline([snap])
    assert timeline["single_snapshot"] is True
    rendered = render_timeline(timeline)
    assert "Only one snapshot" in rendered


def test_missing_generated_at_sorts_last_stably() -> None:
    no_date_1 = _snap("no-date-1", None, (1, 10))
    no_date_2 = _snap("no-date-2", None, (1, 10))
    dated = _snap("dated", "2026-07-30T00:00:00-04:00", (1, 10))
    timeline = build_timeline([no_date_1, no_date_2, dated])
    assert timeline["labels"] == ["dated", "no-date-1", "no-date-2"]


def test_deltas_computed_first_to_last_and_prev_to_last() -> None:
    a = _snap("a", "2026-07-01T00:00:00-04:00", (1, 10))  # unaccounted_rate 0.1
    b = _snap("b", "2026-08-01T00:00:00-04:00", (2, 10))  # unaccounted_rate 0.2
    c = _snap("c", "2026-09-01T00:00:00-04:00", (3, 10))  # unaccounted_rate 0.3
    timeline = build_timeline([a, b, c])
    entry = timeline["metrics"]["unaccounted_rate"]
    assert entry["delta_first_to_last"] == pytest.approx(0.2)
    assert entry["delta_prev_to_last"] == pytest.approx(0.1)
