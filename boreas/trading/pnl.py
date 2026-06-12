"""Paper P&L math for both trading conventions. Pure functions, fully tested.

v1 (da_curve): position taken before the 12:00 CET day-ahead gate against the
baseline B_h.  P&L_h = q_h * (P_da_h - B_h) * 0.25h.
A long position profits when the actual DA price clears above the baseline.

v2 (da_rebap_spread): long/short the spread between reBAP and DA for remaining
quarter-hours.  P&L_h = q_h * (reBAP_h - P_da_h) * 0.25h.
Long spread profits when the imbalance price settles above day-ahead.
"""
from __future__ import annotations

QH_HOURS = 0.25  # one quarter-hour product = 0.25 MWh per MW


def pnl_da_curve(qty_mw: float, da_price: float, baseline: float) -> float:
    return qty_mw * (da_price - baseline) * QH_HOURS


def pnl_da_rebap_spread(qty_mw: float, rebap: float, da_price: float) -> float:
    return qty_mw * (rebap - da_price) * QH_HOURS


def settle(strategy: str, qty_mw: float, ref_price: float, settle_price: float) -> float:
    """Settle one order. ref_price: B_h for v1, DA price for v2. settle_price: DA for v1, reBAP for v2."""
    if strategy == "da_curve":
        return pnl_da_curve(qty_mw, settle_price, ref_price)
    if strategy == "da_rebap_spread":
        return pnl_da_rebap_spread(qty_mw, settle_price, ref_price)
    raise ValueError(f"unknown strategy {strategy!r}")
