"""Reflector: runs when settlements land. Attributes outcomes, journals, evolves the playbook.

The reflection loop is the difference between an agent and a cron job.
"""
from __future__ import annotations

import json
import logging

from boreas import db
from boreas.agents import playbook
from boreas.agents.llm import parse_call
from boreas.agents.schemas import Reflection
from boreas.alerts import telegram
from boreas.config import settings

log = logging.getLogger("boreas.reflector")

SYSTEM = """You are the Reflector of BOREAS, a paper-trading agent for German power. A thesis
has fully settled. Attribute the outcome honestly:
- forecast_wrong: our divergence/nowcast view was wrong about the physics
- sizing_wrong: direction fine, Kelly inputs (confidence/expected move) miscalibrated
- falsifier_ignored: the falsifier fired before delivery and we did not react
- thesis_right: the causal chain played out as described
- noise: P&L dominated by variance unrelated to the thesis
- data_issue: settlement or feature data was wrong/missing

Write a post-mortem journal entry, then decide whether the playbook should change. Propose a
diff ONLY for a transferable lesson, not a description of one trade. Mark structural=true when
the change alters entry/sizing/exit logic rather than adding an observation."""


async def reflect_settled() -> int:
    """Reflect on every settled thesis that has no journal entry yet."""
    p = await db.pool()
    rows = await p.fetch(
        """
        SELECT t.* FROM theses t
        WHERE t.status = 'settled'
          AND NOT EXISTS (SELECT 1 FROM journal_entries j WHERE j.thesis_id = t.id)
        ORDER BY t.created_at
        """)
    for t in rows:
        legs = await p.fetch(
            "SELECT delivery_start, qty_mw, ref_price, settle_price, pnl_eur "
            "FROM paper_orders WHERE thesis_id = $1 ORDER BY delivery_start", t["id"])
        legs_s = "\n".join(
            f"  {r['delivery_start']:%Y-%m-%d %H:%M} qty={r['qty_mw']} ref={r['ref_price']:.1f} "
            f"settle={r['settle_price']:.1f} pnl={r['pnl_eur']:.1f}" for r in legs)
        pb_version, pb_content = await playbook.current()
        thesis_json = json.dumps({
            "strategy": t["strategy"], "direction": t["direction"],
            "delivery_date": str(t["delivery_date"]), "expected_move": t["expected_move"],
            "confidence": t["confidence"], "falsifier": t["falsifier"],
            "rationale": t["rationale"],
        }, indent=2)
        reflection = await parse_call(
            model=settings().reflector_model, system=SYSTEM,
            user=(f"Thesis (created {t['created_at']:%Y-%m-%d %H:%M} UTC):\n{thesis_json}\n\n"
                  f"Settled legs:\n{legs_s}\n\nTotal P&L: {t['pnl_eur']:.1f} EUR\n\n"
                  f"Current playbook (v{pb_version}):\n{pb_content}\n\nReflect."),
            schema=Reflection, max_tokens=2500,
        )
        await p.execute(
            "INSERT INTO journal_entries (thesis_id, content, attribution) VALUES ($1, $2, $3::jsonb)",
            t["id"], reflection.post_mortem,
            json.dumps({"attribution": reflection.attribution}),
        )
        if reflection.playbook_diff and reflection.playbook_diff.new_rules:
            version = await playbook.propose(reflection.playbook_diff)
            if reflection.playbook_diff.structural:
                await telegram.send(
                    f"*BOREAS*: structural playbook change proposed (v{version}) — awaiting approval.\n"
                    f"_{reflection.playbook_diff.rationale}_")
        await telegram.send(
            f"*BOREAS* settled: {t['direction']} {t['strategy']} {t['delivery_date']} "
            f"P&L {t['pnl_eur']:+.0f} EUR — {reflection.attribution}")
        log.info("reflected on thesis %s: %s", t["id"], reflection.attribution)
    return len(rows)
