"""Seam tests for the C++ core's FIFO primitive (docs/scheduler.md).

Skips only if the ``tracon_core`` extension module is not installed."""

import random

import pytest

core = pytest.importorskip("tracon_core", reason="tracon_core extension not installed")


def test_version_is_nonempty_string():
    assert isinstance(core.version(), str)
    assert core.version()


def test_select_fifo_oldest_first_with_stable_ties():
    # indices:              0    1    2    3
    ready = [5.0, 1.0, 3.0, 1.0]
    # the 1.0 tie must resolve lower-index-first: 1 before 3
    assert core.select_fifo(ready, 3) == [1, 3, 2]
    assert core.select_fifo(ready, 4) == [1, 3, 2, 0]


def test_select_fifo_edge_cases():
    assert core.select_fifo([], 4) == []
    assert core.select_fifo([2.0, 1.0], 0) == []
    assert core.select_fifo([2.0, 1.0], 8) == [1, 0]  # k beyond queue: everything


def test_select_fifo_matches_reference_stable_argsort():
    rng = random.Random(1618)  # noqa: S311 — reproducible test data, not crypto
    for _ in range(200):
        n = rng.randrange(40)
        # coarse value pool forces frequent ties so stability is actually exercised
        ready = [rng.choice([0.0, 1.5, 7.25, rng.uniform(0.0, 1e9)]) for _ in range(n)]
        k = rng.randrange(n + 4)
        # sorting (value, index) pairs is a stable argsort: equal values keep index order
        expected = [i for _, i in sorted((r, i) for i, r in enumerate(ready))][:k]
        assert core.select_fifo(ready, k) == expected
