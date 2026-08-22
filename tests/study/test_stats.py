"""Hand-checked tests for tracon.study.stats — no corpus needed."""

from __future__ import annotations

import pytest

from tracon.study.stats import cochran_armitage_trend, quantiles, two_proportion_test, wilson


class TestWilson:
    def test_zero_numerator_lo_is_zero(self):
        r = wilson(0, 100)
        assert r.lo == pytest.approx(0.0, abs=1e-9)
        assert 0.0 <= r.hi <= 1.0
        assert r.numerator == 0
        assert r.denominator == 100
        assert r.value == 0.0

    def test_full_numerator_hi_is_one(self):
        r = wilson(100, 100)
        assert r.hi == 1.0
        assert 0.0 <= r.lo < 1.0
        assert r.value == 1.0

    def test_half_is_symmetric_around_point_five(self):
        r = wilson(50, 100)
        assert r.value == pytest.approx(0.5)
        # Wilson interval for p=0.5 is exactly symmetric: lo + hi == 1.
        assert r.lo + r.hi == pytest.approx(1.0, abs=1e-12)
        assert r.lo < 0.5 < r.hi

    def test_bounds_always_stay_inside_unit_interval(self):
        for num, den in [(0, 1), (1, 1), (1, 3), (2, 3), (999, 1000), (1, 1_000_000)]:
            r = wilson(num, den)
            assert 0.0 <= r.lo <= r.hi <= 1.0

    def test_degenerate_zero_denominator(self):
        r = wilson(0, 0)
        assert r.numerator == 0
        assert r.denominator == 0
        assert r.lo == 0.0
        assert r.hi == 0.0
        assert r.value == 0.0  # guarded division, not a ZeroDivisionError

    def test_negative_denominator_raises(self):
        with pytest.raises(ValueError):
            wilson(1, -1)

    def test_negative_numerator_raises(self):
        with pytest.raises(ValueError):
            wilson(-1, 10)

    def test_numerator_exceeds_denominator_raises(self):
        with pytest.raises(ValueError):
            wilson(11, 10)

    def test_as_dict_shape(self):
        d = wilson(5, 20).as_dict()
        assert set(d) == {"n", "of", "pct", "ci95_pct"}
        assert d["n"] == 5
        assert d["of"] == 20
        assert d["pct"] == pytest.approx(25.0)
        assert len(d["ci95_pct"]) == 2
        assert d["ci95_pct"][0] <= d["pct"] <= d["ci95_pct"][1]

    def test_str_contains_fraction(self):
        s = str(wilson(3, 10))
        assert "n=3/10" in s


class TestTwoProportionTest:
    def test_swapping_arguments_flips_z_sign_keeps_p(self):
        forward = two_proportion_test(10, 100, 30, 100)
        backward = two_proportion_test(30, 100, 10, 100)
        assert forward["z"] == pytest.approx(-backward["z"])
        assert forward["p"] == pytest.approx(backward["p"])
        assert forward["a"] == pytest.approx(backward["b"])
        assert forward["b"] == pytest.approx(backward["a"])

    def test_identical_proportions_give_zero_z(self):
        result = two_proportion_test(20, 100, 20, 100)
        assert result["z"] == pytest.approx(0.0, abs=1e-9)
        assert result["p"] == pytest.approx(1.0)

    def test_a_denominator_zero_returns_neutral(self):
        result = two_proportion_test(0, 0, 5, 10)
        assert result == {"z": 0.0, "p": 1.0, "a": 0.0, "b": 0.0}

    def test_b_denominator_zero_returns_neutral(self):
        result = two_proportion_test(5, 10, 0, 0)
        assert result == {"z": 0.0, "p": 1.0, "a": 0.0, "b": 0.0}

    def test_large_gap_is_significant(self):
        result = two_proportion_test(90, 100, 10, 100)
        assert abs(result["z"]) > 3
        assert result["p"] < 0.01


class TestCochranArmitageTrend:
    def test_flat_series_gives_p_near_one(self):
        rows = [(0.0, 50, 100), (1.0, 50, 100), (2.0, 50, 100)]
        result = cochran_armitage_trend(rows)
        assert result["z"] == pytest.approx(0.0, abs=1e-9)
        assert result["p"] == pytest.approx(1.0, abs=1e-9)

    def test_strictly_decreasing_series_is_significant_negative(self):
        rows = [(0.0, 90, 100), (1.0, 50, 100), (2.0, 10, 100)]
        result = cochran_armitage_trend(rows)
        assert result["z"] < 0
        assert result["p"] < 0.05

    def test_strictly_increasing_series_is_significant_positive(self):
        rows = [(0.0, 10, 100), (1.0, 50, 100), (2.0, 90, 100)]
        result = cochran_armitage_trend(rows)
        assert result["z"] > 0
        assert result["p"] < 0.05

    def test_fewer_than_three_bins_is_too_few(self):
        rows = [(0.0, 10, 100), (1.0, 20, 100)]
        result = cochran_armitage_trend(rows)
        assert result == {"z": 0.0, "p": 1.0, "note": "too few bins"}

    def test_zero_total_rows_are_filtered_before_the_bin_count_check(self):
        rows = [(0.0, 10, 100), (1.0, 20, 100), (2.0, 0, 0)]
        result = cochran_armitage_trend(rows)
        assert result["note"] == "too few bins"

    def test_all_success_is_degenerate(self):
        rows = [(0.0, 100, 100), (1.0, 100, 100), (2.0, 100, 100)]
        result = cochran_armitage_trend(rows)
        assert result == {"z": 0.0, "p": 1.0, "note": "degenerate"}

    def test_all_failure_is_degenerate(self):
        rows = [(0.0, 0, 100), (1.0, 0, 100), (2.0, 0, 100)]
        result = cochran_armitage_trend(rows)
        assert result == {"z": 0.0, "p": 1.0, "note": "degenerate"}


class TestQuantiles:
    def test_known_list_nearest_rank(self):
        values = [float(x) for x in range(1, 11)]  # 1..10
        result = quantiles(values)
        assert result["p50"] == 5.0
        assert result["p90"] == 9.0
        assert result["p95"] == 10.0
        assert result["p99"] == 10.0
        assert result["max"] == 10.0

    def test_empty_input_yields_empty_dict(self):
        assert quantiles([]) == {}

    def test_custom_points(self):
        values = [10.0, 20.0, 30.0, 40.0]
        result = quantiles(values, points=(0.25, 0.5))
        # ceil(0.25*4)-1 = 0 -> 10.0 ; ceil(0.5*4)-1 = 1 -> 20.0
        assert result["p25"] == 10.0
        assert result["p50"] == 20.0
        assert result["max"] == 40.0

    def test_unsorted_input_is_sorted_before_ranking(self):
        values = [5.0, 1.0, 3.0, 2.0, 4.0]
        result = quantiles(values, points=(1.0,))
        assert result["p100"] == 5.0
        assert result["max"] == 5.0

    def test_single_value(self):
        result = quantiles([42.0])
        assert all(v == 42.0 for v in result.values())
