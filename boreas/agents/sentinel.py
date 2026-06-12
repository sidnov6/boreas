"""Sentinel: deterministic rules + a Haiku call. The cost gate — 90% of cycles end here."""
from __future__ import annotations

import logging

from boreas.agents.llm import parse_call
from boreas.agents.schemas import SentinelVerdict
from boreas.config import settings
from boreas.features.frame import FeatureFrame

log = logging.getLogger("boreas.sentinel")

SYSTEM = """You are the Sentinel of BOREAS, an autonomous paper-trading agent for the German
power market. You classify a 15-minute feature snapshot as one of:
- "nothing": normal conditions, no follow-up
- "interesting": a signal is building but not actionable yet
- "act_worthy": a tradeable dislocation is likely; wake the Analyst

Be conservative: "act_worthy" should fire on a minority of snapshots. The strongest signals are
a wind/solar divergence z-score beyond ±2 (BOREAS's own nowcast disagrees with the TSO forecast),
persistent one-directional forecast-error trend into a ramp window, and a steep merit-order regime
amplifying any MW error into EUR."""


def deterministic_screen(frame: FeatureFrame) -> str | None:
    """Cheap rules that bypass the LLM entirely. Returns a verdict or None to escalate."""
    wz = frame.wind_divergence.zscore
    sz = frame.solar_divergence.zscore
    we = frame.wind_error.trend_mw_per_h
    big_divergence = (wz is not None and abs(wz) >= 2.0) or (sz is not None and abs(sz) >= 2.0)
    strong_trend = we is not None and abs(we) >= 500.0  # MW/h sustained error drift
    big_ramp = frame.ramp_coincidence is not None and frame.ramp_coincidence >= 6000.0

    if not any([big_divergence, strong_trend, big_ramp]):
        return "nothing"  # ~90% of cycles end here, zero LLM cost
    return None  # ambiguous — let Haiku decide between interesting / act_worthy


async def classify(frame: FeatureFrame) -> SentinelVerdict:
    screened = deterministic_screen(frame)
    if screened is not None:
        return SentinelVerdict(level=screened, reason="deterministic screen: no triggers")
    verdict = await parse_call(
        model=settings().sentinel_model,
        system=SYSTEM,
        user=f"Feature snapshot:\n{frame.model_dump_json(indent=2)}\n\nClassify it.",
        schema=SentinelVerdict,
        max_tokens=300,
    )
    log.info("sentinel: %s (%s)", verdict.level, verdict.reason)
    return verdict
