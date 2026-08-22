"""Small, dependency-free statistics, lifted verbatim from agentfail's ``stats.py``.

Only ``Z95``, ``Rate``, ``wilson()``, ``normal_sf()``, and ``two_proportion_test()`` are copied
here — the rest of that module is agentfail-specific. agent-obs and agentfail deliberately do not
depend on each other, so this copy is kept in sync by hand.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Z95 = 1.959963984540054


@dataclass(frozen=True)
class Rate:
    """A proportion with a Wilson score interval."""

    numerator: int
    denominator: int
    lo: float
    hi: float

    @property
    def value(self) -> float:
        return self.numerator / self.denominator if self.denominator else 0.0

    @property
    def pct(self) -> float:
        return 100.0 * self.value

    def as_dict(self) -> dict:
        return {
            "n": self.numerator,
            "of": self.denominator,
            "pct": round(self.pct, 3),
            "ci95_pct": [round(100 * self.lo, 3), round(100 * self.hi, 3)],
        }

    def __str__(self) -> str:
        return f"{self.pct:.2f}% [{100*self.lo:.2f}–{100*self.hi:.2f}] (n={self.numerator}/{self.denominator})"


def wilson(numerator: int, denominator: int, z: float = Z95) -> Rate:
    """Wilson score interval for a binomial proportion.

    Preferred over the normal approximation because several rates in this study
    are near zero (identical-shape retries, unmatched calls) where the normal
    interval runs below 0 and stops meaning anything.
    """
    if denominator < 0 or numerator < 0 or numerator > denominator:
        raise ValueError("need 0 <= numerator <= denominator")
    if denominator == 0:
        return Rate(0, 0, 0.0, 0.0)
    p = numerator / denominator
    z2 = z * z
    centre = p + z2 / (2 * denominator)
    spread = z * math.sqrt((p * (1 - p) + z2 / (4 * denominator)) / denominator)
    denom = 1 + z2 / denominator
    lo = max(0.0, (centre - spread) / denom)
    hi = min(1.0, (centre + spread) / denom)
    return Rate(numerator, denominator, lo, hi)


def normal_sf(x: float) -> float:
    """Upper tail of the standard normal."""
    return 0.5 * math.erfc(x / math.sqrt(2))


def two_proportion_test(a_num: int, a_den: int, b_num: int, b_den: int) -> dict:
    """Two-sided two-proportion z-test (pooled). Returns z and p."""
    if a_den == 0 or b_den == 0:
        return {"z": 0.0, "p": 1.0, "a": 0.0, "b": 0.0}
    p1, p2 = a_num / a_den, b_num / b_den
    pooled = (a_num + b_num) / (a_den + b_den)
    se = math.sqrt(pooled * (1 - pooled) * (1 / a_den + 1 / b_den))
    if se == 0:
        return {"z": 0.0, "p": 1.0, "a": p1, "b": p2}
    z = (p1 - p2) / se
    return {"z": z, "p": 2 * normal_sf(abs(z)), "a": p1, "b": p2}
