"""Paper book: open orders from approved theses, settle them when prices land."""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta

from boreas import db
from boreas.trading import pnl as pnl_mod

log = logging.getLogger("boreas.book")


async def open_orders_for_thesis(thesis_id: str, strategy: str, delivery: date,
                                 qh_indices: list[int], qty_mw_signed: float) -> int:
    """Create one paper order per quarter-hour. ref_price is captured at open:
    v1 uses the baseline B_h, v2 uses the DA price for that quarter-hour."""
    day_start = datetime.combine(delivery, time(0, 0), tzinfo=UTC)
    ref_series = "price.baseline" if strategy == "da_curve" else "price.da"
    refs = await db.latest_series(ref_series, day_start, day_start + timedelta(days=1))
    p = await db.pool()
    n = 0
    for qh in qh_indices:
        start = day_start + timedelta(minutes=15 * qh)
        ref = refs.get(start)
        if ref is None:
            log.warning("no %s for %s qh%d; skipping leg", ref_series, delivery, qh)
            continue
        await p.execute(
            """
            INSERT INTO paper_orders (thesis_id, strategy, delivery_start, delivery_end, qty_mw, ref_price)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            thesis_id, strategy, start, start + timedelta(minutes=15), qty_mw_signed, ref,
        )
        n += 1
    return n


async def settle_due_orders() -> list[dict]:
    """Settle open orders whose settlement price has been published.

    v1 settles on the actual DA price (lands ~13:00 CET day before delivery);
    v2 settles on preliminary reBAP (publication lag: verify in week one).
    """
    p = await db.pool()
    open_orders = await p.fetch(
        "SELECT * FROM paper_orders WHERE status = 'open' AND delivery_end < now() ORDER BY delivery_start")
    settled: list[dict] = []
    for o in open_orders:
        series = "price.da" if o["strategy"] == "da_curve" else "rebap"
        prices = await db.latest_series(series, o["delivery_start"],
                                        o["delivery_start"] + timedelta(minutes=15))
        price = prices.get(o["delivery_start"]) or (next(iter(prices.values())) if prices else None)
        if price is None:
            continue  # settlement data not published yet
        value = pnl_mod.settle(o["strategy"], o["qty_mw"], o["ref_price"], price)
        await p.execute(
            """UPDATE paper_orders SET status='settled', settle_price=$2, pnl_eur=$3, settled_at=now()
               WHERE id=$1""",
            o["id"], price, value,
        )
        settled.append({**dict(o), "settle_price": price, "pnl_eur": value})
    if settled:
        # Roll up thesis P&L and mark fully-settled theses.
        await p.execute(
            """
            UPDATE theses t SET
                pnl_eur = s.total,
                status = CASE WHEN s.open_legs = 0 THEN 'settled' ELSE t.status END
            FROM (
                SELECT thesis_id, SUM(pnl_eur) AS total,
                       COUNT(*) FILTER (WHERE status = 'open') AS open_legs
                FROM paper_orders GROUP BY thesis_id
            ) s
            WHERE t.id = s.thesis_id
            """)
        log.info("settled %d order legs", len(settled))
    return settled


async def book_state(as_of_day: date | None = None) -> dict:
    """Open exposure + today's realized P&L for the Risk Officer."""
    p = await db.pool()
    day = as_of_day or datetime.now(UTC).date()
    gross = await p.fetchval(
        "SELECT COALESCE(SUM(ABS(qty_mw)), 0) FROM paper_orders WHERE status='open'")
    open_theses = await p.fetchval(
        "SELECT COUNT(*) FROM theses WHERE status IN ('approved', 'live')")
    realized = await p.fetchval(
        "SELECT COALESCE(SUM(pnl_eur), 0) FROM paper_orders WHERE settled_at::date = $1", day)
    return {"gross_open_mw": float(gross), "open_theses": int(open_theses),
            "realized_pnl_today": float(realized)}
