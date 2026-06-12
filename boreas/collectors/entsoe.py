"""ENTSO-E Transparency Platform collector (zone DE-LU).

Document types collected:
  A65 actual load, A65(forecast) day-ahead load forecast,
  A75 actual generation per type (wind on/offshore, solar),
  A69 TSO wind/solar day-ahead + intraday forecasts,
  A44 day-ahead prices.

Uses entsoe-py (sync, pandas) wrapped in asyncio.to_thread.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pandas as pd

from boreas.config import settings
from boreas.collectors.base import store
from boreas.db import Obs

log = logging.getLogger("boreas.collect.entsoe")

ZONE = "DE_LU"
SOURCE = "entsoe"

GEN_TYPE_SERIES = {
    "Wind Onshore": "wind_onshore.actual",
    "Wind Offshore": "wind_offshore.actual",
    "Solar": "solar.actual",
}
FORECAST_COL_SERIES = {
    "Wind Onshore": "wind_onshore.forecast",
    "Wind Offshore": "wind_offshore.forecast",
    "Solar": "solar.forecast",
}


def _client():
    from entsoe import EntsoePandasClient

    key = settings().entsoe_api_key
    if not key:
        raise RuntimeError("ENTSOE_API_KEY not set")
    return EntsoePandasClient(api_key=key)


def _rows_from_series(s: pd.Series, series_id: str, unit: str = "MW") -> list[Obs]:
    rows: list[Obs] = []
    for ts, val in s.items():
        if pd.isna(val):
            continue
        rows.append(Obs(series_id=series_id, ts_event=ts.to_pydatetime().astimezone(UTC),
                        value=float(val), unit=unit, source=SOURCE))
    return rows


def _fetch_window(start: pd.Timestamp, end: pd.Timestamp) -> list[Obs]:
    client = _client()
    cc = "DE_LU"
    rows: list[Obs] = []

    # Actual load (A65) + load forecast
    try:
        load = client.query_load(cc, start=start, end=end)["Actual Load"]
        rows += _rows_from_series(load, "load.actual")
    except Exception as e:  # noqa: BLE001 — each query degrades independently
        log.warning("load.actual failed: %s", e)
    try:
        lf = client.query_load_forecast(cc, start=start, end=end)
        col = lf.columns[0] if isinstance(lf, pd.DataFrame) else None
        rows += _rows_from_series(lf[col] if col else lf, "load.forecast")
    except Exception as e:  # noqa: BLE001
        log.warning("load.forecast failed: %s", e)

    # Actual generation per type (A75)
    try:
        gen = client.query_generation(cc, start=start, end=end, psr_type=None)
        if isinstance(gen.columns, pd.MultiIndex):
            gen.columns = [" ".join(str(p) for p in c if p and "Consumption" not in str(p)).strip()
                           for c in gen.columns]
        for col_name, series_id in GEN_TYPE_SERIES.items():
            match = [c for c in gen.columns if str(c).startswith(col_name)]
            if match:
                rows += _rows_from_series(gen[match[0]].dropna(), series_id)
    except Exception as e:  # noqa: BLE001
        log.warning("generation actuals failed: %s", e)

    # TSO wind/solar forecasts (A69)
    try:
        wsf = client.query_wind_and_solar_forecast(cc, start=start, end=end)
        for col_name, series_id in FORECAST_COL_SERIES.items():
            if col_name in wsf.columns:
                rows += _rows_from_series(wsf[col_name].dropna(), series_id)
    except Exception as e:  # noqa: BLE001
        log.warning("wind/solar forecast failed: %s", e)

    # Day-ahead prices (A44) — 15-min products since Oct 2025
    try:
        da = client.query_day_ahead_prices(cc, start=start, end=end)
        rows += _rows_from_series(da, "price.da", unit="EUR/MWh")
    except Exception as e:  # noqa: BLE001
        log.warning("day-ahead prices failed: %s", e)

    return rows


async def collect(hours_back: int = 48, hours_fwd: int = 36) -> int:
    """Regular cycle: trailing window for actuals + forward window for forecasts/DA."""
    now = pd.Timestamp(datetime.now(UTC))
    rows = await asyncio.to_thread(
        _fetch_window, now - pd.Timedelta(hours=hours_back), now + pd.Timedelta(hours=hours_fwd)
    )
    return await store(rows, "entsoe")


async def backfill(days: int = 365, chunk_days: int = 30) -> int:
    """Historical backfill in monthly chunks (rate-limit friendly)."""
    end = datetime.now(UTC)
    total = 0
    cursor = end - timedelta(days=days)
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=chunk_days), end)
        rows = await asyncio.to_thread(_fetch_window, pd.Timestamp(cursor), pd.Timestamp(chunk_end))
        total += await store(rows, "entsoe")
        log.info("backfill %s → %s done", cursor.date(), chunk_end.date())
        cursor = chunk_end
        await asyncio.sleep(2)
    return total
