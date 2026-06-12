"""Typed FeatureFrame — the single artifact the agent society reasons over."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pydantic import BaseModel, Field


class ForecastError(BaseModel):
    """Trailing forecast error stats for one series (actual - forecast, MW)."""

    current_mw: float | None = None
    mean_3h_mw: float | None = None
    mean_6h_mw: float | None = None
    trend_mw_per_h: float | None = None  # slope of error over trailing 6h


class Divergence(BaseModel):
    """BOREAS nowcast vs TSO forecast for the same horizon."""

    boreas_mw: float | None = None
    tso_mw: float | None = None
    delta_mw: float | None = None
    zscore: float | None = None  # vs trailing 30d distribution of deltas


class FeatureFrame(BaseModel):
    ts: datetime
    zone: str = "DE_LU"

    wind_error: ForecastError = Field(default_factory=ForecastError)
    solar_error: ForecastError = Field(default_factory=ForecastError)
    load_error: ForecastError = Field(default_factory=ForecastError)

    residual_load_mw: float | None = None          # load - wind - solar (the real price driver)
    residual_load_forecast_mw: float | None = None
    ramp_coincidence: float | None = None          # solar drop-off ramp + wind ramp overlap, MW/h

    wind_divergence: Divergence = Field(default_factory=Divergence)
    solar_divergence: Divergence = Field(default_factory=Divergence)

    nrv_saldo_mw: float | None = None
    da_price_eur: float | None = None
    ttf_eur: float | None = None
    eua_eur: float | None = None
    merit_order_steep: bool | None = None          # gas-on-the-margin regime

    def hash(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def headline(self) -> str:
        """One-line summary used in sentinel prompts and alerts."""
        wz = self.wind_divergence.zscore
        we = self.wind_error.current_mw
        return (
            f"resid_load={_fmt(self.residual_load_mw)}MW "
            f"wind_err={_fmt(we)}MW wind_div_z={_fmt(wz, 2)} "
            f"ramp={_fmt(self.ramp_coincidence)}MW/h nrv={_fmt(self.nrv_saldo_mw)}MW "
            f"da={_fmt(self.da_price_eur, 1)}€ steep_merit={self.merit_order_steep}"
        )


def _fmt(v: float | None, nd: int = 0) -> str:
    return "n/a" if v is None else f"{v:.{nd}f}"
