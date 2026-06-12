"""Executor: deterministic, no LLM. Approved thesis -> paper orders with full lineage."""
from __future__ import annotations

import json
import logging
from datetime import date

from boreas import db
from boreas.agents.schemas import Thesis
from boreas.alerts import telegram
from boreas.config import settings
from boreas.features.frame import FeatureFrame
from boreas.trading.book import open_orders_for_thesis

log = logging.getLogger("boreas.executor")


async def execute(thesis: Thesis, qty_mw: float, risk_note: str,
                  frame: FeatureFrame, playbook_version: int) -> str:
    """Persist the thesis with lineage (feature hash, playbook + prompt versions), open orders, alert."""
    signed_qty = qty_mw if thesis.direction == "long" else -qty_mw
    p = await db.pool()
    thesis_id = await p.fetchval(
        """
        INSERT INTO theses (status, strategy, direction, delivery_date, qh_indices, expected_move,
                            confidence, falsifier, rationale, feature_ts, feature_hash,
                            playbook_version, prompt_version, raw, risk_note)
        VALUES ('live', $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, $14)
        RETURNING id
        """,
        thesis.strategy, thesis.direction, date.fromisoformat(thesis.delivery_date),
        thesis.qh_indices, thesis.expected_move_eur_mwh, thesis.confidence,
        thesis.falsifier, thesis.rationale, frame.ts, frame.hash(),
        playbook_version, settings().prompt_version,
        json.dumps(thesis.model_dump(mode="json")), risk_note,
    )
    n_legs = await open_orders_for_thesis(
        thesis_id, thesis.strategy, date.fromisoformat(thesis.delivery_date),
        thesis.qh_indices, signed_qty,
    )
    qh = thesis.qh_indices
    await telegram.send(
        f"*BOREAS*: {thesis.direction} {thesis.strategy} "
        f"Q{min(qh)}–Q{max(qh)} {thesis.delivery_date} @ {qty_mw} MW/qh ({n_legs} legs)\n"
        f"_{thesis.rationale[:300]}_\n"
        f"Falsifier: {thesis.falsifier}"
    )
    log.info("executed thesis %s: %d legs at %s MW/qh", thesis_id, n_legs, qty_mw)
    return str(thesis_id)
