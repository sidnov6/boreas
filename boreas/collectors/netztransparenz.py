"""Netztransparenz API collector: NRV-Saldo (live system imbalance) and reBAP.

Requires free client-credentials registration at https://api-portal.netztransparenz.de.
Degrades gracefully (logs + skips) when credentials are absent, so the rest of
BOREAS runs without it. Week-one job: verify reBAP publication lag against this
feed — it decides whether the Reflector for v2 runs T+2 or T+5.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, datetime, timedelta, timezone

import httpx

from boreas.config import settings
from boreas.collectors.base import store
from boreas.db import Obs

log = logging.getLogger("boreas.collect.netztransparenz")

TOKEN_URL = "https://identity.netztransparenz.de/users/connect/token"
BASE = "https://ds.netztransparenz.de/api/v1"
SOURCE = "netztransparenz"


async def _token(client: httpx.AsyncClient) -> str | None:
    s = settings()
    if not s.netztransparenz_client_id:
        log.info("netztransparenz credentials not set; skipping")
        return None
    r = await client.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": s.netztransparenz_client_id,
        "client_secret": s.netztransparenz_client_secret,
    })
    r.raise_for_status()
    return r.json()["access_token"]


def _parse_csv(text: str, series_id: str, unit: str) -> list[Obs]:
    """Netztransparenz CSVs: semicolon-separated, German decimal comma, local time columns."""
    rows: list[Obs] = []
    reader = csv.reader(io.StringIO(text), delimiter=";")
    header = next(reader, None)
    if not header:
        return rows
    for rec in reader:
        if len(rec) < 4:
            continue
        try:
            # Columns: Datum;von;Zeitzone von;bis;...;Wert  (value is last non-empty cell)
            date_s, from_s = rec[0], rec[1]
            ts = datetime.strptime(f"{date_s} {from_s}", "%d.%m.%Y %H:%M")
            # Files state CET/CEST per row; approximate with fixed +1/+2 from the tz column.
            tz_s = rec[2].strip() if len(rec) > 2 else "CET"
            offset = 2 if "CEST" in tz_s or "MESZ" in tz_s else 1
            ts = ts.replace(tzinfo=timezone(timedelta(hours=offset))).astimezone(UTC)
            val_s = next((c for c in reversed(rec) if c.strip()), "")
            val = float(val_s.replace(".", "").replace(",", "."))
        except (ValueError, StopIteration):
            continue
        rows.append(Obs(series_id=series_id, ts_event=ts, value=val, unit=unit, source=SOURCE))
    return rows


async def collect(days_back: int = 7) -> int:
    now = datetime.now(UTC)
    start = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%S")
    end = now.strftime("%Y-%m-%dT%H:%M:%S")
    rows: list[Obs] = []
    async with httpx.AsyncClient(timeout=60) as client:
        tok = await _token(client)
        if tok is None:
            return 0
        headers = {"Authorization": f"Bearer {tok}"}
        for path, series_id, unit in (
            (f"/data/NrvSaldo/Saldo/{start}/{end}", "nrv_saldo", "MW"),
            (f"/data/reBAP/{start}/{end}", "rebap", "EUR/MWh"),
        ):
            try:
                r = await client.get(BASE + path, headers=headers)
                r.raise_for_status()
                rows += _parse_csv(r.text, series_id, unit)
            except httpx.HTTPError as e:
                log.warning("%s failed: %s", path, e)
    return await store(rows, "netztransparenz")
