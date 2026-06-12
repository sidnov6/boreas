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

    # --- agent activity: every cycle is visible, including the ones that decide 'nothing' ---
    runs = await p.fetch(
        """
        SELECT r.id, r.kind, r.feature_ts, r.sentinel_verdict, r.detail, r.started_at,
               f.frame
        FROM agent_runs r
        LEFT JOIN feature_frames f ON f.ts = r.feature_ts
        ORDER BY r.started_at DESC
        LIMIT 96
        """)
    cycles = []
    for r in runs:
        detail = json.loads(r["detail"]) if r["detail"] else {}
        frame = json.loads(r["frame"]) if r["frame"] else {}
        cycles.append({
            "ts": (r["feature_ts"] or r["started_at"]).isoformat(),
            "kind": r["kind"],
            "verdict": r["sentinel_verdict"],
            "reason": detail.get("verdict_reason"),
            "thesis_id": detail.get("thesis_id"),
            "pass_reason": detail.get("pass_reason"),
            "wind_div_z": (frame.get("wind_divergence") or {}).get("zscore"),
            "residual_load_mw": frame.get("residual_load_mw"),
            "da_price_eur": frame.get("da_price_eur"),
        })

    latest_frame = await p.fetchrow("SELECT ts, frame FROM feature_frames ORDER BY ts DESC LIMIT 1")
    n_obs = await p.fetchval("SELECT COUNT(*) FROM observations")
    system_now = None
    if latest_frame:
        f = json.loads(latest_frame["frame"])
        system_now = {
            "ts": latest_frame["ts"].isoformat(),
            "residual_load_mw": f.get("residual_load_mw"),
            "wind_div_z": (f.get("wind_divergence") or {}).get("zscore"),
            "solar_div_z": (f.get("solar_divergence") or {}).get("zscore"),
            "wind_err_mw": (f.get("wind_error") or {}).get("current_mw"),
            "da_price_eur": f.get("da_price_eur"),
            "ramp_mw_h": f.get("ramp_coincidence"),
            "n_observations": int(n_obs),
        }
    activity = {"generated_at": datetime.now(UTC).isoformat(), "system_now": system_now,
                "cycles": cycles}

    out = _out_dir()
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    (out / "theses.json").write_text(json.dumps(theses_out, indent=1))
    (out / "playbook.json").write_text(json.dumps(playbook_out, indent=1))
    (out / "activity.json").write_text(json.dumps(activity, indent=1))
    log.info("report exported to %s (%d theses, %d playbook versions, %d cycles)",
             out, len(theses_out), len(playbook_out), len(cycles))
    return summary
