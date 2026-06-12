"""One async process runs everything: collectors, feature engine, agent cycles, settlement,
reflection, reporting — each on its own cadence via APScheduler."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from boreas import db
from boreas.agents import graph as agent_graph
from boreas.agents import reflector
from boreas.baseline import model as baseline
from boreas.collectors import energy_charts, entsoe, markets, netztransparenz, open_meteo
from boreas.features import engine as feature_engine
from boreas.reporting import reporter

log = logging.getLogger("boreas.scheduler")


async def _safe(coro_fn, name: str, *args, **kwargs):
    try:
        await coro_fn(*args, **kwargs)
    except Exception:  # noqa: BLE001 — one failing job must not kill the process
        log.exception("job %s failed", name)


async def features_and_cycle():
    frame = await feature_engine.run_cycle()
    await agent_graph.run_cycle(frame)


async def baseline_tomorrow():
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date()
    await baseline.predict_day(tomorrow)


def build_scheduler() -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone="UTC")
    add = sched.add_job

    # Layer 1: collectors, each source on its own cadence with rate-limit awareness.
    add(_safe, "cron", minute="2,17,32,47", args=[entsoe.collect, "entsoe"], id="entsoe")
    add(_safe, "cron", minute="4,19,34,49", args=[energy_charts.collect, "energy_charts"], id="echarts")
    add(_safe, "cron", minute="0,30", args=[energy_charts.collect_forecasts, "energy_charts_fc"],
        id="echarts_fc")
    add(_safe, "cron", minute=8, args=[open_meteo.collect, "open_meteo"], id="meteo")
    add(_safe, "cron", minute="6,21,36,51", args=[netztransparenz.collect, "netztransparenz"], id="ntp")
    add(_safe, "cron", hour=6, minute=10, args=[markets.collect, "markets"], id="markets")

    # Layer 3+4: features then the agent society, after collectors land.
    add(_safe, "cron", minute="10,25,40,55", args=[features_and_cycle, "cycle"], id="cycle")

    # Baseline B_h for tomorrow, before the 12:00 CET day-ahead gate.
    add(_safe, "cron", hour=9, minute=30, args=[baseline_tomorrow, "baseline"], id="baseline")

    # Settlement + reflection.
    from boreas.trading.book import settle_due_orders
    add(_safe, "cron", minute=20, args=[settle_due_orders, "settle"], id="settle")
    add(_safe, "cron", minute=45, args=[reflector.reflect_settled, "reflect"], id="reflect")

    # Tearsheet regeneration + public site redeploy (report JSON -> next build -> HF Space).
    add(_safe, "cron", hour=22, minute=30, args=[reporter.export_all, "report"], id="report")
    add(_safe, "cron", hour="1,7,13,19", minute=50, args=[deploy_site, "deploy_site"], id="deploy")
    return sched


async def deploy_site():
    """Rebuild and push the track-record site so the public record stays current."""
    proc = await asyncio.create_subprocess_exec(
        "bash", "scripts/deploy_site.sh",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await proc.communicate()
    tail = out.decode(errors="replace").strip().splitlines()[-3:]
    log.info("deploy_site rc=%s: %s", proc.returncode, " | ".join(tail))


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    await db.init_db()
    sched = build_scheduler()
    sched.start()
    log.info("BOREAS scheduler up: %d jobs", len(sched.get_jobs()))
    try:
        await asyncio.Event().wait()
    finally:
        sched.shutdown(wait=False)
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
