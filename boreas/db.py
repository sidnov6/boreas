"""Database layer: asyncpg pool, vintage-preserving observation store, LISTEN/NOTIFY."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import asyncpg

from boreas.config import settings

_pool: asyncpg.Pool | None = None


async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(settings().database_url, min_size=1, max_size=8)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def init_db() -> None:
    schema = (Path(__file__).resolve().parent.parent / "db" / "schema.sql").read_text()
    p = await pool()
    await p.execute(schema)


@dataclass(frozen=True)
class Obs:
    """Canonical observation row."""

    series_id: str
    ts_event: datetime
    value: float | None
    source: str
    unit: str = ""
    model_run: str = ""
    zone: str = "DE_LU"


async def insert_observations(rows: list[Obs], ts_published: datetime) -> int:
    """Insert observations, preserving vintages without storing redundant copies.

    A row is written only if its value differs from the latest stored vintage for
    that (series_id, zone, ts_event, model_run, source). This is what makes any
    past day replayable exactly as the agents saw it live.
    """
    if not rows:
        return 0
    p = await pool()
    inserted = 0
    async with p.acquire() as con:
        latest = await con.fetch(
            """
            SELECT DISTINCT ON (series_id, zone, ts_event, model_run, source)
                   series_id, zone, ts_event, model_run, source, value
            FROM observations
            WHERE (series_id, zone, ts_event, model_run, source) = ANY(
                SELECT * FROM unnest($1::text[], $2::text[], $3::timestamptz[], $4::text[], $5::text[])
            )
            ORDER BY series_id, zone, ts_event, model_run, source, ts_published DESC
            """,
            [r.series_id for r in rows],
            [r.zone for r in rows],
            [r.ts_event for r in rows],
            [r.model_run for r in rows],
            [r.source for r in rows],
        )
        known = {
            (rec["series_id"], rec["zone"], rec["ts_event"], rec["model_run"], rec["source"]): rec["value"]
            for rec in latest
        }
        new = [
            r
            for r in rows
            if known.get((r.series_id, r.zone, r.ts_event, r.model_run, r.source), object()) != r.value
        ]
        if new:
            await con.executemany(
                """
                INSERT INTO observations (series_id, zone, ts_event, ts_published, model_run, value, unit, source)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (series_id, zone, ts_event, ts_published, model_run, source) DO NOTHING
                """,
                [
                    (r.series_id, r.zone, r.ts_event, ts_published, r.model_run, r.value, r.unit, r.source)
                    for r in new
                ],
            )
            inserted = len(new)
    return inserted


async def latest_series(
    series_id: str,
    start: datetime,
    end: datetime,
    as_of: datetime | None = None,
    source: str | None = None,
) -> dict[datetime, float]:
    """Latest vintage of a series over [start, end), optionally as seen at `as_of` (replay)."""
    p = await pool()
    q = """
        SELECT DISTINCT ON (ts_event) ts_event, value
        FROM observations
        WHERE series_id = $1 AND ts_event >= $2 AND ts_event < $3
          AND ($4::timestamptz IS NULL OR ts_published <= $4)
          AND ($5::text IS NULL OR source = $5)
        ORDER BY ts_event, ts_published DESC
    """
    recs = await p.fetch(q, series_id, start, end, as_of, source)
    return {r["ts_event"]: r["value"] for r in recs if r["value"] is not None}


async def notify(channel: str, payload: dict) -> None:
    p = await pool()
    await p.execute("SELECT pg_notify($1, $2)", channel, json.dumps(payload, default=str))
