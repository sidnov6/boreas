"""TTF gas + EUA carbon (daily, delayed) for merit-order regime context."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC

from boreas.config import settings
from boreas.collectors.base import store
from boreas.db import Obs

log = logging.getLogger("boreas.collect.markets")

SOURCE = "yahoo"


def _fetch(ticker: str, series_id: str, period: str) -> list[Obs]:
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False)
    rows: list[Obs] = []
    for ts, rec in hist.iterrows():
        close = rec.get("Close")
        if close is None or close != close:  # NaN
            continue
        ts_utc = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        rows.append(Obs(series_id=series_id, ts_event=ts_utc.to_pydatetime().astimezone(UTC),
                        value=float(close), unit="EUR", source=SOURCE))
    return rows


async def collect(period: str = "3mo") -> int:
    s = settings()
    rows: list[Obs] = []
    for ticker, series_id in ((s.ttf_ticker, "ttf.close"), (s.eua_ticker, "eua.close")):
        try:
            rows += await asyncio.to_thread(_fetch, ticker, series_id, period)
        except Exception as e:  # noqa: BLE001 — yahoo is flaky, regime context is optional
            log.warning("%s failed: %s", ticker, e)
    return await store(rows, "markets")
