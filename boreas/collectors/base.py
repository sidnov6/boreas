from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from boreas.config import settings
from boreas.db import Obs, insert_observations

log = logging.getLogger("boreas.collect")


def utcnow() -> datetime:
    return datetime.now(UTC)


async def store(rows: list[Obs], collector: str) -> int:
    n = await insert_observations(rows, ts_published=utcnow())
    log.info("%s: %d new vintage rows (%d fetched)", collector, n, len(rows))
    await ping_healthcheck(collector)
    return n


async def ping_healthcheck(slug: str) -> None:
    """Dead-man switch: ping healthchecks.io on every successful collector cycle."""
    url = settings().healthchecks_url
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.get(url.rstrip("/"), params={"rid": slug})
    except httpx.HTTPError:  # monitoring must never break collection
        log.warning("healthchecks ping failed for %s", slug)
