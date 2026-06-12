"""Telegram alerts — the phone-buzzing-mid-interview channel."""
from __future__ import annotations

import logging

import httpx

from boreas.config import settings

log = logging.getLogger("boreas.telegram")


async def send(text: str) -> bool:
    s = settings()
    if not s.telegram_bot_token or not s.telegram_chat_id:
        log.info("telegram not configured; alert suppressed: %s", text[:120])
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage",
                json={"chat_id": s.telegram_chat_id, "text": text, "parse_mode": "Markdown"},
            )
            r.raise_for_status()
        return True
    except httpx.HTTPError as e:
        log.warning("telegram send failed: %s", e)
        return False
