"""Competent baseline: rolling 90-day regression from TSO-forecast residual load to DA price.

P&L for v1 is measured against this, not lazy persistence. Per quarter-hour-of-day
regression P_qh = a_qh + b_qh * residual_load_forecast_qh, refit daily on the
trailing window. Beating it means genuine forecast edge.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

import numpy as np

from boreas import db
from boreas.db import Obs

log = logging.getLogger("boreas.baseline")

QH_PER_DAY = 96


@dataclass
class QhModel:
    intercept: float
    slope: float

    def predict(self, residual_load_mw: float) -> float:
        return self.intercept + self.slope * residual_load_mw


def fit_qh_models(samples: dict[int, list[tuple[float, float]]],
                  min_samples: int = 20) -> dict[int, QhModel]:
    """Fit per-quarter-hour OLS models from (residual_load, price) samples."""
    models: dict[int, QhModel] = {}
    # Pool across all hours as fallback for sparse quarter-hours.
    pooled = [s for lst in samples.values() for s in lst]
    pooled_model = _ols(pooled) if len(pooled) >= min_samples else None
    for qh in range(QH_PER_DAY):
        pts = samples.get(qh, [])
        if len(pts) >= min_samples:
            models[qh] = _ols(pts)
        elif pooled_model is not None:
            models[qh] = pooled_model
    return models


def _ols(pts: list[tuple[float, float]]) -> QhModel:
    x = np.array([p[0] for p in pts])
    y = np.array([p[1] for p in pts])
    if np.std(x) < 1e-9:
        return QhModel(intercept=float(np.mean(y)), slope=0.0)
    slope, intercept = np.polyfit(x, y, 1)
    return QhModel(intercept=float(intercept), slope=float(slope))


async def _residual_load_forecast(start: datetime, end: datetime) -> dict[datetime, float]:
    """Forecast residual load; for history beyond the forecast archive, fall back to
    actuals (a fine proxy for fitting — forecast ≈ actual at the daily-shape level)."""
    out: dict[datetime, float] = {}
    for suffix in (".forecast", ".actual"):
        load = await db.latest_series(f"load{suffix}", start, end)
        won = await db.latest_series(f"wind_onshore{suffix}", start, end)
        woff = await db.latest_series(f"wind_offshore{suffix}", start, end)
        sol = await db.latest_series(f"solar{suffix}", start, end)
        for ts, lv in load.items():
            if ts in out:
                continue  # forecast (first pass) wins
            s = sol.get(ts)
            if s is None:
                continue
            out[ts] = lv - won.get(ts, 0.0) - woff.get(ts, 0.0) - s
    return out


async def fit(window_days: int = 90) -> dict[int, QhModel]:
    end = datetime.now(UTC)
    start = end - timedelta(days=window_days)
    resid = await _residual_load_forecast(start, end)
    price = await db.latest_series("price.da", start, end)
    samples: dict[int, list[tuple[float, float]]] = {}
    for ts, p in price.items():
        r = resid.get(ts)
        if r is None:
            # 15-min residual data may be hourly: try the top of the hour.
            r = resid.get(ts.replace(minute=0))
        if r is None:
            continue
        qh = ts.hour * 4 + ts.minute // 15
        samples.setdefault(qh, []).append((r, p))
    models = fit_qh_models(samples)
    log.info("baseline fit: %d/%d quarter-hours, %d samples",
             len(models), QH_PER_DAY, sum(len(v) for v in samples.values()))
    return models


async def predict_day(delivery: date) -> dict[datetime, float]:
    """Predict B_h for every quarter-hour of `delivery`, store as price.baseline vintages."""
    models = await fit()
    if not models:
        return {}
    day_start = datetime.combine(delivery, time(0, 0), tzinfo=UTC)
    resid = await _residual_load_forecast(day_start, day_start + timedelta(days=1))
    preds: dict[datetime, float] = {}
    for qh in range(QH_PER_DAY):
        ts = day_start + timedelta(minutes=15 * qh)
        model = models.get(qh)
        r = resid.get(ts) or resid.get(ts.replace(minute=0))
        if model is None or r is None:
            continue
        preds[ts] = model.predict(r)
    if preds:
        rows = [Obs(series_id="price.baseline", ts_event=ts, value=v, unit="EUR/MWh", source="boreas")
                for ts, v in preds.items()]
        await db.insert_observations(rows, ts_published=datetime.now(UTC))
    log.info("baseline predicted %d quarter-hours for %s", len(preds), delivery)
    return preds
