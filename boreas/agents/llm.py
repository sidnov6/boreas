"""Anthropic client helpers: structured calls via client.messages.parse (Pydantic-validated)."""
from __future__ import annotations

import asyncio
import logging
from typing import TypeVar

from pydantic import BaseModel

from boreas.config import settings

log = logging.getLogger("boreas.llm")

T = TypeVar("T", bound=BaseModel)

_client = None


def client():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(api_key=settings().anthropic_api_key or None)
    return _client


async def parse_call(model: str, system: str, user: str, schema: type[T],
                     max_tokens: int = 2000) -> T:
    """Structured-output call; the API validates against the schema so we never parse by regex."""

    def _call() -> T:
        resp = client().messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_format=schema,
        )
        return resp.parsed_output

    return await asyncio.to_thread(_call)
