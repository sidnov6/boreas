"""Energy-Charts (Fraunhofer ISE) collector — the no-auth pipe.

Free JSON API: https://api.energy-charts.info
Provides actuals, day-ahead prices AND the TSO forecasts, so the whole feature
pipeline (divergence, residual load, baseline) runs without an ENTSO-E key.
The API rate-limits aggressively: keep calls sequential with spacing.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import httpx

from boreas.collectors.base import store
from boreas.db import Obs

log = logging.getLogger("boreas.collect.energy_charts")

BASE = "https://api.energy-charts.info"
SOURCE = "energy_charts"
CALL_SPACING_S = 4.0

PROD_SERIES = {
    "Wind onshore": "wind_onshore.actual",
    "Wind offshore": "wind_offshore.actual",
    "Solar": "solar.actual",
    "Load": "load.actual",
}

# TSO forecasts: forecast_type "current" is the latest TSO view (revision stream,
# vintage-tracked by our store); "day-ahead" is the auction-relevant vintage.
FORECAST_TYPES = {
    "current": ".forecast",
    "day-ahead": ".forecast_da",
}
FORECAST_PROD = {
    "wind_onshore": "wind_onshore",
    "wind_offshore": "wind_offshore",
    "solar": "solar",
    "load": "load",
}


def _ts(unix: int) -> datetime:
    return datetime.fromtimestamp(unix, tz=UTC)


async def _get_json(client: httpx.AsyncClient, path: str, params: dict, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            r = await client.get(f"{BASE}{path}", params=params)
            if r.status_code == 429:
                await asyncio.sleep(15 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning("%s %s failed: %s", path, params, e)
            await asyncio.sleep(5)
    return None


def _series_arrays(data: dict) -> tuple[list[datetime], list[float | None]]:
    """Forecast payloads carry unix_seconds plus one value array (name varies)."""
    stamps = [_ts(u) for u in data.get("unix_seconds", [])]
    values: list = []
    for key, val in data.items():
        if key != "unix_seconds" and isinstance(val, list) and len(val) == len(stamps):
            values = val
            break
    return stamps, values


async def collect_forecasts() -> int:
    """TSO wind/solar/load forecasts via Energy-Charts (keyless ENTSO-E A69 substitute)."""
    rows: list[Obs] = []
    async with httpx.AsyncClient(timeout=60) as client:
        for ftype, suffix in FORECAST_TYPES.items():
            for prod, series_base in FORECAST_PROD.items():
                data = await _get_json(client, "/public_power_forecast",
                                       {"country": "de", "production_type": prod, "forecast_type": ftype})
                await asyncio.sleep(CALL_SPACING_S)
                if not data:
                    continue
                stamps, values = _series_arrays(data)
                for ts, val in zip(stamps, values):
                    if val is not None:
                        rows.append(Obs(series_id=f"{series_base}{suffix}", ts_event=ts,
                                        value=float(val), unit="MW", source=SOURCE))
    return await store(rows, "energy_charts_fc")


async def backfill(days: int = 365, chunk_days: int = 30) -> int:
    """Historical actuals + DA prices, keyless — enough to train the baseline."""
    end = datetime.now(UTC)
    cursor = end - timedelta(days=days)
    total = 0
    async with httpx.AsyncClient(timeout=120) as client:
        while cursor < end:
            chunk_end = min(cursor + timedelta(days=chunk_days), end)
            params = {"country": "de", "start": cursor.strftime("%Y-%m-%d"),
                      "end": chunk_end.strftime("%Y-%m-%d")}
            rows: list[Obs] = []
            data = await _get_json(client, "/public_power", params)
            await asyncio.sleep(CALL_SPACING_S)
            if data:
                stamps = [_ts(u) for u in data.get("unix_seconds", [])]
                for pt in data.get("production_types", []):
                    series_id = PROD_SERIES.get(pt["name"])
                    if not series_id:
                        continue
                    for ts, val in zip(stamps, pt["data"]):
                        if val is not None:
                            rows.append(Obs(series_id=series_id, ts_event=ts, value=float(val),
                                            unit="MW", source=SOURCE))
            pdata = await _get_json(client, "/price", {"bzn": "DE-LU", **params})
            await asyncio.sleep(CALL_SPACING_S)
            if pdata:
                for ts_u, val in zip(pdata.get("unix_seconds", []), pdata.get("price", [])):
                    if val is not None:
                        rows.append(Obs(series_id="price.da", ts_event=_ts(ts_u), value=float(val),
                                        unit="EUR/MWh", source=SOURCE))
            total += await store(rows, "energy_charts_backfill")
            log.info("backfill %s -> %s done", cursor.date(), chunk_end.date())
            cursor = chunk_end
    return total


async def collect(hours_back: int = 48) -> int:
    now = datetime.now(UTC)
    start = (now - timedelta(hours=hours_back)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    rows: list[Obs] = []

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.get(f"{BASE}/public_power", params={"country": "de", "start": start, "end": end})
            r.raise_for_status()
            data = r.json()
            stamps = [_ts(u) for u in data["unix_seconds"]]
            for pt in data.get("production_types", []):
                series_id = PROD_SERIES.get(pt["name"])
                if not series_id:
                    continue
                for ts, val in zip(stamps, pt["data"]):
                    if val is not None:
                        rows.append(Obs(series_id=series_id, ts_event=ts, value=float(val),
                                        unit="MW", source=SOURCE))
        except (httpx.HTTPError, KeyError, ValueError) as e:
            log.warning("public_power failed: %s", e)

        try:
            r = await client.get(f"{BASE}/price", params={"bzn": "DE-LU", "start": start, "end": end})
            r.raise_for_status()
            data = r.json()
            for ts_u, val in zip(data["unix_seconds"], data["price"]):
                if val is not None:
                    rows.append(Obs(series_id="price.da", ts_event=_ts(ts_u), value=float(val),
                                    unit="EUR/MWh", source=SOURCE))
        except (httpx.HTTPError, KeyError, ValueError) as e:
            log.warning("price failed: %s", e)

    return await store(rows, "energy_charts")
