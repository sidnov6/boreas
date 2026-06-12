"""Nightly Reporter: regenerates the static JSON the track-record site renders.

Outputs (site/public/data/):
  summary.json   — headline stats + equity curve vs flat baseline
  theses.json    — every decision, expandable to its full reasoning chain
  playbook.json  — versioned changelog showing the agent getting smarter
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from boreas import db
from boreas.config import settings

log = logging.getLogger("boreas.reporter")


def _out_dir() -> Path:
    d = Path(settings().site_data_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


async def export_all() -> dict:
    p = await db.pool()

    # --- equity curve: cumulative realized P&L by settlement day ---
    daily = await p.fetch(
        """
        SELECT settled_at::date AS day, SUM(pnl_eur) AS pnl
        FROM paper_orders WHERE status = 'settled'
        GROUP BY 1 ORDER BY 1
        """)
    curve, cum = [], 0.0
    for r in daily:
        cum += float(r["pnl"])
        curve.append({"date": r["day"].isoformat(), "pnl": round(float(r["pnl"]), 2),
                      "cumulative": round(cum, 2)})

    stats = await p.fetchrow(
        """
        SELECT COUNT(*) FILTER (WHERE status = 'settled')                    AS n_settled,
               COUNT(*) FILTER (WHERE status = 'settled' AND pnl_eur > 0)    AS n_wins,
               COALESCE(SUM(pnl_eur) FILTER (WHERE status = 'settled'), 0)   AS total_pnl,
               COUNT(*) FILTER (WHERE status = 'live')                       AS n_live
        FROM theses
        """)
    n = int(stats["n_settled"]) or 0
    pnls = [float(r["pnl"]) for r in daily]
    sharpe = None
    if len(pnls) >= 5:
        import statistics as st

        sd = st.pstdev(pnls)
        if sd > 1e-9:
            sharpe = round(st.fmean(pnls) / sd * (365 ** 0.5), 2)
    max_dd = 0.0
    peak = 0.0
    for pt in curve:
        peak = max(peak, pt["cumulative"])
        max_dd = min(max_dd, pt["cumulative"] - peak)

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_pnl_eur": round(float(stats["total_pnl"]), 2),
        "n_theses_settled": n,
        "n_theses_live": int(stats["n_live"]),
        "hit_rate": round(int(stats["n_wins"]) / n, 3) if n else None,
        "sharpe_daily_annualized": sharpe,
        "max_drawdown_eur": round(max_dd, 2),
        "equity_curve": curve,
    }

    # --- theses with full reasoning lineage ---
    theses = await p.fetch(
        """
        SELECT t.*, COALESCE(j.content, '') AS post_mortem,
               COALESCE(j.attribution ->> 'attribution', '') AS attribution
        FROM theses t
        LEFT JOIN journal_entries j ON j.thesis_id = t.id
        ORDER BY t.created_at DESC
        LIMIT 500
        """)
    theses_out = [{
        "id": str(t["id"]),
        "created_at": t["created_at"].isoformat(),
        "status": t["status"],
        "strategy": t["strategy"],
        "direction": t["direction"],
        "delivery_date": t["delivery_date"].isoformat(),
        "qh_indices": list(t["qh_indices"]),
        "expected_move": t["expected_move"],
        "confidence": t["confidence"],
        "falsifier": t["falsifier"],
        "rationale": t["rationale"],
        "risk_note": t["risk_note"],
        "pnl_eur": round(t["pnl_eur"], 2) if t["pnl_eur"] is not None else None,
        "feature_hash": t["feature_hash"],
        "playbook_version": t["playbook_version"],
        "prompt_version": t["prompt_version"],
        "post_mortem": t["post_mortem"],
        "attribution": t["attribution"],
    } for t in theses]

    # --- playbook changelog ---
    pb = await p.fetch("SELECT * FROM playbook_versions ORDER BY version DESC")
    playbook_out = [{
        "version": r["version"],
        "created_at": r["created_at"].isoformat(),
        "rationale": r["rationale"],
        "diff": r["diff"],
        "auto_merged": r["auto_merged"],
        "approved": r["approved"],
        "content": r["content"],
    } for r in pb]

    out = _out_dir()
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    (out / "theses.json").write_text(json.dumps(theses_out, indent=1))
    (out / "playbook.json").write_text(json.dumps(playbook_out, indent=1))
    log.info("report exported to %s (%d theses, %d playbook versions)",
             out, len(theses_out), len(playbook_out))
    return summary
