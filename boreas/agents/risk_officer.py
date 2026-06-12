"""Risk Officer: capped fractional Kelly inside hard-coded limits.

The limits live in code; the LLM only argues within them — its commentary can veto,
never raise, the deterministic size.
"""
from __future__ import annotations

import logging

from boreas.agents.llm import parse_call
from boreas.agents.schemas import RiskCommentary, Thesis
from boreas.config import settings
from boreas.trading.book import book_state
from boreas.trading.limits import LIMITS, check_thesis, kelly_size_mw

log = logging.getLogger("boreas.risk")

SYSTEM = """You are the Risk Officer of BOREAS, a paper-trading agent for German power.
You receive a thesis already sized by capped fractional Kelly inside hard-coded limits.
You CANNOT change the size. You can only flag concerns or veto a trade that is unsound
(internally inconsistent thesis, falsifier that cannot fire in time, stale features,
correlation with existing open theses). Veto sparingly but decisively."""


async def review(thesis: Thesis) -> tuple[bool, float, str]:
    """Returns (approved, qty_mw, note)."""
    state = await book_state()
    qty = kelly_size_mw(thesis.confidence, thesis.expected_move_eur_mwh)
    ok, reason = check_thesis(
        qty_mw=qty, n_qh=len(thesis.qh_indices),
        open_theses=state["open_theses"], gross_open_mw=state["gross_open_mw"],
        realized_pnl_today=state["realized_pnl_today"],
    )
    if not ok:
        log.info("risk: hard limit rejection — %s", reason)
        return False, 0.0, f"hard limit: {reason}"

    commentary = await parse_call(
        model=settings().analyst_model, system=SYSTEM,
        user=(f"Thesis:\n{thesis.model_dump_json(indent=2)}\n\n"
              f"Computed size: {qty} MW per quarter-hour across {len(thesis.qh_indices)} quarter-hours.\n"
              f"Book state: {state}\nLimits: {LIMITS}\n\nReview."),
        schema=RiskCommentary, max_tokens=600,
    )
    note = f"kelly={qty}MW/qh; " + ("; ".join(commentary.concerns) or "no concerns")
    if not commentary.proceed:
        log.info("risk: LLM veto — %s", note)
        return False, 0.0, "veto: " + note
    return True, qty, note
