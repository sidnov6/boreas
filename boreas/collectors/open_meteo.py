"""Open-Meteo collector wrapping DWD ICON-D2: hub-height wind + irradiance per site.

Free, no key. ICON-D2 updates ~every 3h at ~2km resolution over Germany.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from boreas.collectors.base import store
from boreas.db import Obs
from boreas.mastr.sites import SITES

log = logging.getLogger("boreas.collect.open_meteo")

BASE = "https://api.open-meteo.com/v1/forecast"
SOURCE = "open_meteo"
HOURLY = "wind_speed_100m,wind_speed_120m,shortwave_radiation"


def _model_run(now: datetime) -> str:
    """ICON-D2 runs every 3h; tag vintages with the latest plausible run."""
    h = (now.hour // 3) * 3
    return now.strftime(f"%Y-%m-%dT{h:02d}Z")


async def collect() -> int:
    now = datetime.now(UTC)
    run = _model_run(now)
    rows: list[Obs] = []
    async with httpx.AsyncClient(timeout=60) as client:
        # Open-Meteo accepts comma-separated coordinate lists — one call for all sites.
        params = {
            "latitude": ",".join(f"{s.lat:.2f}" for s in SITES),
            "longitude": ",".join(f"{s.lon:.2f}" for s in SITES),
            "hourly": HOURLY,
            "models": "icon_d2",
            "forecast_days": 2,
            "timeformat": "unixtime",
            "timezone": "UTC",
        }
        r = await client.get(BASE, params=params)
        r.raise_for_status()
        payload = r.json()
        results = payload if isinstance(payload, list) else [payload]
        for site, res in zip(SITES, results):
            hourly = res.get("hourly", {})
            stamps = [datetime.fromtimestamp(u, tz=UTC) for u in hourly.get("time", [])]
            for var, series in (
                ("wind_speed_100m", f"meteo.wind100m.{site.id}"),
                ("wind_speed_120m", f"meteo.wind120m.{site.id}"),
                ("shortwave_radiation", f"meteo.ghi.{site.id}"),
            ):
                vals = hourly.get(var) or []
                unit = "m/s" if "wind" in var else "W/m2"
                for ts, v in zip(stamps, vals):
                    if v is not None:
                        rows.append(Obs(series_id=series, ts_event=ts, value=float(v),
                                        unit=unit, model_run=run, source=SOURCE))
    return await store(rows, "open_meteo")
