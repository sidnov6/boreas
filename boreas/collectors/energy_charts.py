"""Energy-Charts (Fraunhofer ISE) collector — the no-auth redundancy pipe.

Free JSON API: https://api.energy-charts.info
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx

from boreas.collectors.base import store
from boreas.db import Obs

log = logging.getLogger("boreas.collect.energy_charts")

BASE = "https://api.energy-charts.info"
SOURCE = "energy_charts"

PROD_SERIES = {
    "Wind onshore": "wind_onshore.actual",
    "Wind offshore": "wind_offshore.actual",
    "Solar": "solar.actual",
    "Load": "load.actual",
}


def _ts(unix: int) -> datetime:
    return datetime.fromtimestamp(unix, tz=UTC)


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
