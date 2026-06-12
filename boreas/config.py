from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://boreas:boreas@localhost:5433/boreas"

    entsoe_api_key: str = ""
    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    netztransparenz_client_id: str = ""
    netztransparenz_client_secret: str = ""
    healthchecks_url: str = ""

    boreas_zone: str = "DE_LU"
    boreas_timezone: str = "Europe/Berlin"

    # LLM models. Sentinel gate is cheap+fast; Analyst/Reflector need reasoning.
    sentinel_model: str = "claude-haiku-4-5"
    analyst_model: str = "claude-sonnet-4-6"
    reflector_model: str = "claude-sonnet-4-6"

    # Yahoo tickers for merit-order regime context. CO2.L is a carbon ETC used
    # as a free EUA proxy; swap for a licensed EUA feed if you get one.
    ttf_ticker: str = "TTF=F"
    eua_ticker: str = "CO2.L"

    site_data_dir: str = "site/public/data"
    prompt_version: str = "p1"


@lru_cache
def settings() -> Settings:
    return Settings()
