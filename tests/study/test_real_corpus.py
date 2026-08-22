"""Invariant checks against the real tracon export.

These never assert a memorized number — the corpus changes over time. Instead
they assert structural invariants that must hold for any honest report: every
rate's numerator fits inside its denominator, every CI contains its point
estimate, the looping lower bound never exceeds the upper bound, long-tail
composition shares sum to ~100%, and the overall error rate is a sane
percentage.

Skipped cleanly (not failed) when the real export directory does not exist,
so the suite is green on any machine.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tracon.cli import main as tracon_main
from tracon.study import cli, loader

REAL_TRACE = Path(
    os.environ.get("TRACON_STUDY_TRACE", "traces/export-2026-07-30"),
).expanduser()

pytestmark = pytest.mark.slow

_missing_reason = f"real trace export not found at {REAL_TRACE}"


def _corpus_available() -> bool:
    return (REAL_TRACE / "events.jsonl").exists()


@pytest.fixture(scope="module")
def result():
    if not _corpus_available():
        pytest.skip(_missing_reason)
    return cli.run(REAL_TRACE)


def _walk_rate_dicts(node):
    """Yield every dict in the (possibly nested) result tree that looks like
    a Rate.as_dict() output: {"n", "of", "pct", "ci95_pct"}."""
    if isinstance(node, dict):
        if {"n", "of", "pct", "ci95_pct"} <= set(node):
            yield node
        for value in node.values():
            yield from _walk_rate_dicts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_rate_dicts(item)


class TestLoadsCleanly:
    def test_corpus_loads_without_error(self):
        if not _corpus_available():
            pytest.skip(_missing_reason)
        corpus = loader.load(REAL_TRACE)
        assert len(corpus.streams) > 0
        assert corpus.manifest  # non-empty manifest.json exists


class TestRateInvariants:
    def test_every_rate_numerator_within_denominator(self, result):
        rates = list(_walk_rate_dicts(result))
        assert rates, "expected at least one Rate dict in the real report"
        for r in rates:
            assert 0 <= r["n"] <= r["of"], r

    def test_every_ci_contains_its_point_estimate(self, result):
        rates = list(_walk_rate_dicts(result))
        for r in rates:
            lo, hi = r["ci95_pct"]
            # small tolerance for the rounding baked into as_dict()
            assert lo - 1e-6 <= r["pct"] <= hi + 1e-6, r

    def test_every_ci_bounds_are_within_zero_to_hundred_pct(self, result):
        for r in _walk_rate_dicts(result):
            lo, hi = r["ci95_pct"]
            assert 0.0 <= lo <= hi <= 100.0, r


class TestLoopingBounds:
    def test_lower_bound_le_upper_bound_calls_in_runs(self, result):
        loop = result["looping"]
        lower = loop["lower_bound"]["share_of_calls_inside_a_repeat_run"]["n"]
        upper = loop["upper_bound"]["share_of_calls_inside_a_repeat_run"]["n"]
        assert lower <= upper

    def test_lower_bound_le_upper_bound_run_count(self, result):
        loop = result["looping"]
        assert loop["lower_bound"]["runs"] <= loop["upper_bound"]["runs"]

    def test_lower_bound_le_upper_bound_stuck_streams(self, result):
        loop = result["looping"]
        lower = loop["lower_bound"]["share_of_streams_with_a_stuck_run"]["n"]
        upper = loop["upper_bound"]["share_of_streams_with_a_stuck_run"]["n"]
        assert lower <= upper


class TestLongtailComposition:
    def test_composition_by_calls_shares_sum_near_100(self, result):
        tiers = result["longtail"]["tiers"]
        assert tiers, "expected at least one long-tail tier in the real corpus"
        for tier_name, tier in tiers.items():
            total_pct = sum(v["pct"] for v in tier["composition_by_calls"].values())
            assert total_pct == pytest.approx(100.0, abs=0.5), (tier_name, total_pct)

    def test_composition_by_time_shares_sum_near_100(self, result):
        tiers = result["longtail"]["tiers"]
        for tier_name, tier in tiers.items():
            total_pct = sum(tier["composition_by_time_pct"].values())
            assert total_pct == pytest.approx(100.0, abs=0.5), (tier_name, total_pct)


class TestErrorRateSanity:
    def test_overall_error_rate_between_zero_and_hundred(self, result):
        rate = result["errors"]["overall_error_rate"]
        assert 0.0 <= rate["pct"] <= 100.0

    def test_error_rate_by_tool_all_sane(self, result):
        for tool, rate in result["errors"]["error_rate_by_tool"].items():
            assert 0.0 <= rate["pct"] <= 100.0, tool
            assert rate["n"] <= rate["of"]


class TestConsistencyAcrossCliEntryPoints:
    def test_check_against_freshly_written_result_matches(self, tmp_path):
        if not _corpus_available():
            pytest.skip(_missing_reason)
        stored = tmp_path / "stored.json"
        rc_write = tracon_main(
            ["study", "report", "--trace", str(REAL_TRACE), "--json", str(stored)]
        )
        assert rc_write == 0
        rc_check = tracon_main(
            ["study", "report", "--trace", str(REAL_TRACE), "--check", str(stored)]
        )
        assert rc_check == 0  # the report is deterministic given the same export
