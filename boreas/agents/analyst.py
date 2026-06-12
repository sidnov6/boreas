"""Analyst: wakes on Sentinel triggers, pulls context through tools, emits a structured Thesis."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from boreas import db
from boreas.agents import playbook
from boreas.agents.llm import parse_call
from boreas.agents.schemas import AnalystOutput
from boreas.config import settings
from boreas.features.analogs import top_analogs
from boreas.features.frame import FeatureFrame

log = logging.getLogger("boreas.analyst")

SYSTEM = """You are the Analyst of BOREAS, an autonomous PAPER-trading agent for German power
(zone DE-LU, 96 quarter-hour day-ahead products). You receive a feature snapshot, analog days,
recent price behaviour and the current playbook. Decide whether there is a tradeable thesis.

Strategies available:
- "da_curve": before the 12:00 CET day-ahead auction gate, position q_h for tomorrow's delivery
  quarter-hours; P&L = q * (P_DA - baseline). Use when you believe tomorrow's auction will clear
  away from the residual-load-regression baseline (e.g. the TSO wind forecast is wrong).
- "da_rebap_spread": intraday, long/short the spread reBAP minus DA for remaining quarter-hours
  of TODAY; use when live NRV-Saldo and forecast-error accumulation point to a persistent system
  imbalance direction.

Rules:
- Only output a thesis you would defend to a risk officer. If the setup is muddy, has_thesis=false.
- expected_move_eur_mwh must be consistent with direction (positive = price above reference for
  long, i.e. the side you profit on).
- The falsifier must be observable BEFORE delivery (a model run revision, NRV flip, error reversal).
- Respect the playbook; it encodes lessons from settled trades."""


async def _recent_price_context(now: datetime) -> str:
    da = await db.latest_series("price.da", now - timedelta(days=3), now + timedelta(days=1))
    if not da:
        return "No recent DA prices available."
    vals = list(da.values())
    return (f"DA price last 3d: min {min(vals):.1f}, max {max(vals):.1f}, "
            f"mean {sum(vals)/len(vals):.1f} EUR/MWh, last {vals[-1]:.1f}")


async def _analog_context(now: datetime) -> str:
    """Nearest-neighbour analog days by residual-load forecast shape."""
    day0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    target_day = day0 + timedelta(days=1)
    target = await _daily_residual_shape(target_day)
    if len(target) < 12:
        return "Insufficient forward data for analog matching."
    candidates: dict[str, list[float]] = {}
    for d in range(2, 60):
        day = day0 - timedelta(days=d)
        shape = await _daily_residual_shape(day)
        if len(shape) >= 12:
            candidates[day.date().isoformat()] = shape
    if not candidates:
        return "No analog history yet."
    analogs = top_analogs(target, candidates, k=5)
    lines = []
    for day_s, dist in analogs:
        day = datetime.fromisoformat(day_s).replace(tzinfo=UTC)
        prices = await db.latest_series("price.da", day, day + timedelta(days=1))
        if prices:
            pv = list(prices.values())
            lines.append(f"  {day_s} (dist {dist:.2f}): DA min {min(pv):.0f} / max {max(pv):.0f} "
                         f"/ mean {sum(pv)/len(pv):.0f} EUR/MWh")
        else:
            lines.append(f"  {day_s} (dist {dist:.2f}): no price data")
    return "Top analog days by residual-load shape:\n" + "\n".join(lines)


async def _daily_residual_shape(day: datetime) -> list[float]:
    end = day + timedelta(days=1)
    load = await db.latest_series("load.forecast", day, end)
    won = await db.latest_series("wind_onshore.forecast", day, end)
    woff = await db.latest_series("wind_offshore.forecast", day, end)
    sol = await db.latest_series("solar.forecast", day, end)
    shape = []
    for ts in sorted(load):
        s = sol.get(ts)
        if s is None:
            continue
        shape.append(load[ts] - won.get(ts, 0.0) - woff.get(ts, 0.0) - s)
    return shape


async def analyze(frame: FeatureFrame) -> tuple[AnalystOutput, int]:
    pb_version, pb_content = await playbook.current()
    now = frame.ts
    user = "\n\n".join([
        f"Current time (UTC): {now.isoformat()}",
        f"Feature snapshot:\n{frame.model_dump_json(indent=2)}",
        await _recent_price_context(now),
        await _analog_context(now),
        f"Current playbook (v{pb_version}):\n{pb_content}",
        "Produce your decision.",
    ])
    out = await parse_call(
        model=settings().analyst_model, system=SYSTEM, user=user,
        schema=AnalystOutput, max_tokens=3000,
    )
    if out.has_thesis and out.thesis:
        log.info("analyst thesis: %s %s qh=%s conf=%.2f",
                 out.thesis.direction, out.thesis.strategy,
                 out.thesis.qh_indices[:4], out.thesis.confidence)
    else:
        log.info("analyst passed: %s", out.pass_reason)
    return out, pb_version
