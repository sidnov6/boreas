"""Logistic power curve: hub-height wind speed -> fleet capacity factor.

Fleet-aggregate curves are smoother than single-turbine curves; a logistic with
cut-in/cut-out handling is the standard cheap approximation.
"""
from __future__ import annotations

import math

CUT_IN = 3.0      # m/s
RATED = 12.0      # m/s — fleet reaches ~rated output
CUT_OUT = 25.0    # m/s
STEEPNESS = 0.65  # logistic slope


def capacity_factor(wind_ms: float) -> float:
    """Capacity factor in [0, 1] for a regional fleet at given hub-height wind speed."""
    if wind_ms is None or wind_ms < CUT_IN:
        return 0.0
    if wind_ms >= CUT_OUT:
        return 0.0  # storm shutdown
    cf = 1.0 / (1.0 + math.exp(-STEEPNESS * (wind_ms - (CUT_IN + RATED) / 2.0)))
    return max(0.0, min(1.0, cf))


def fleet_generation_mw(wind_by_site: dict[str, float], capacity_gw_by_site: dict[str, float]) -> float:
    """Capacity-weighted nowcast in MW across sites."""
    total = 0.0
    for site_id, gw in capacity_gw_by_site.items():
        w = wind_by_site.get(site_id)
        if w is None:
            continue
        total += capacity_factor(w) * gw * 1000.0
    return total


def solar_generation_mw(ghi_by_site: dict[str, float], capacity_gw_by_site: dict[str, float],
                        performance_ratio: float = 0.85) -> float:
    """Crude GHI->PV conversion: cf ≈ PR * GHI / 1000 W/m²."""
    total = 0.0
    for site_id, gw in capacity_gw_by_site.items():
        ghi = ghi_by_site.get(site_id)
        if ghi is None:
            continue
        cf = max(0.0, min(1.0, performance_ratio * ghi / 1000.0))
        total += cf * gw * 1000.0
    return total
