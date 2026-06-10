"""Depreciation curve fitting and threshold forecasting.

Model: annual sports titles drop fast after launch, then flatten toward a
floor. We fit an exponential decay toward a floor:

    price(t) = floor + (p0 - floor) * exp(-k * t)

where t is days since release. Parameters are fit by pooling the daily-low
price points from all *past* editions, then the fitted curve is applied to the
current edition to forecast when it crosses key price thresholds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import curve_fit

from .data_sources import PricePoint


@dataclass(frozen=True)
class CurveParams:
    floor: float   # asymptotic minimum price
    p0: float      # modeled launch price (t=0)
    k: float       # decay rate per day
    n_points: int  # how many observations the fit used

    def price_at(self, days: float) -> float:
        return self.floor + (self.p0 - self.floor) * math.exp(-self.k * days)

    def days_to_price(self, target: float) -> float | None:
        """Days since release at which the curve first reaches `target`.

        Returns None if the target is at/below the floor (never reached) or
        above the modeled launch price (already there at launch).
        """
        if target <= self.floor:
            return None
        if target >= self.p0:
            return 0.0
        ratio = (target - self.floor) / (self.p0 - self.floor)
        return -math.log(ratio) / self.k


def to_cumulative_min(points: list[PricePoint]) -> list[PricePoint]:
    """Best (lowest) price available by each day — a clean downward curve.

    Annual sports titles sit at full price most days with occasional sale dips.
    For "when does it first hit $X" the decision-relevant series is the lowest
    price seen so far, which is what we both plot and fit.
    """
    out: list[PricePoint] = []
    running = float("inf")
    for p in sorted(points, key=lambda x: x.days_since_release):
        running = min(running, p.price)
        out.append(PricePoint(p.days_since_release, round(running, 2)))
    return out


def first_crossing_day(points: list[PricePoint], threshold: float) -> int | None:
    """Day on which observed price first fell to/below `threshold` (or None)."""
    for p in to_cumulative_min(points):
        if p.price <= threshold:
            return p.days_since_release
    return None


def _decay(t, floor, p0, k):
    return floor + (p0 - floor) * np.exp(-k * t)


def fit_curve(points: list[PricePoint], msrp: float) -> CurveParams:
    """Fit the decay model to pooled price points.

    Falls back to a simple anchored estimate if the optimizer can't converge
    (e.g. too few points), so the app always has something to plot.
    """
    if len(points) < 4:
        raise ValueError("Not enough price history to fit a depreciation curve.")

    t = np.array([p.days_since_release for p in points], dtype=float)
    y = np.array([p.price for p in points], dtype=float)

    # Bounds keep the fit physically sensible: a floor between $5 and $45, a
    # launch price near MSRP, and a gentle-to-moderate daily decay rate.
    bounds = ([5.0, msrp * 0.7, 1e-4], [45.0, msrp * 1.05, 0.05])
    p_guess = [20.0, msrp, 0.01]

    try:
        popt, _ = curve_fit(_decay, t, y, p0=p_guess, bounds=bounds, maxfev=10000)
        floor, p0, k = popt
    except Exception:
        # Coarse fallback: floor = observed min, decay anchored to the data span.
        floor = max(5.0, float(y.min()))
        p0 = float(msrp)
        span = max(t.max(), 30.0)
        # Pick k so the curve reaches ~halfway to the floor across the span.
        k = math.log(2) / (span / 2)

    return CurveParams(floor=float(floor), p0=float(p0), k=float(k), n_points=len(points))


def curve_line(params: CurveParams, max_days: int, step: int = 5) -> tuple[list[int], list[float]]:
    """Sampled (days, price) pairs for plotting the fitted curve."""
    xs = list(range(0, max_days + 1, step))
    ys = [round(params.price_at(d), 2) for d in xs]
    return xs, ys
