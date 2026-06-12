"""Hard-coded risk limits. The limits live in code; the LLM only argues within them."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskLimits:
    max_mw_per_qh: float = 25.0        # per quarter-hour position cap
    max_gross_mw_day: float = 600.0    # sum of |qty| across all open quarter-hours per day
    max_concurrent_theses: int = 3
    daily_stop_eur: float = -2000.0    # realized P&L stop; no new theses below this
    kelly_fraction: float = 0.25       # capped fractional Kelly
    assumed_price_sd_eur: float = 25.0 # typical DA quarter-hour dispersion vs baseline


LIMITS = RiskLimits()


def kelly_size_mw(confidence: float, expected_move_eur: float,
                  limits: RiskLimits = LIMITS) -> float:
    """Capped fractional Kelly translated to MW per quarter-hour.

    Treat the thesis as a bet with win prob p=confidence and payoff ratio
    b = |expected_move| / assumed_sd. Kelly f* = p - (1-p)/b, floored at 0,
    scaled by kelly_fraction, mapped onto the per-qh MW cap.
    """
    p = max(0.0, min(1.0, confidence))
    b = abs(expected_move_eur) / limits.assumed_price_sd_eur
    if b <= 0:
        return 0.0
    f_star = p - (1.0 - p) / b
    if f_star <= 0:
        return 0.0
    return round(min(f_star * limits.kelly_fraction, 1.0) * limits.max_mw_per_qh, 1)


def check_thesis(qty_mw: float, n_qh: int, open_theses: int, gross_open_mw: float,
                 realized_pnl_today: float, limits: RiskLimits = LIMITS) -> tuple[bool, str]:
    """Deterministic gate. Returns (approved, reason)."""
    if realized_pnl_today <= limits.daily_stop_eur:
        return False, f"daily stop hit ({realized_pnl_today:.0f} EUR <= {limits.daily_stop_eur:.0f})"
    if open_theses >= limits.max_concurrent_theses:
        return False, f"max concurrent theses ({limits.max_concurrent_theses}) reached"
    if qty_mw <= 0:
        return False, "Kelly size is zero — edge too small for the assumed variance"
    if qty_mw > limits.max_mw_per_qh:
        return False, f"qty {qty_mw} MW exceeds per-qh cap {limits.max_mw_per_qh}"
    if gross_open_mw + qty_mw * n_qh > limits.max_gross_mw_day:
        return False, f"gross cap {limits.max_gross_mw_day} MW would be exceeded"
    return True, "within limits"
