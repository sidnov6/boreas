"""BOREAS command line. `boreas --help` for the map."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import typer

app = typer.Typer(help="BOREAS — German intraday power market paper-trading agent")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


def _run(coro):
    return asyncio.run(coro)


@app.command()
def init_db():
    """Create extensions, hypertables and all tables."""
    from boreas import db

    async def go():
        await db.init_db()
        await db.close_pool()
        typer.echo("schema applied")

    _run(go())


@app.command()
def backfill(days: int = typer.Option(365, help="days of ENTSO-E history")):
    """12-month historical backfill (ENTSO-E in monthly chunks + markets)."""
    from boreas import db
    from boreas.collectors import entsoe, markets

    async def go():
        await db.init_db()
        await markets.collect(period="2y")
        await entsoe.backfill(days=days)
        await db.close_pool()

    _run(go())


@app.command()
def collect():
    """Run every collector once."""
    from boreas import db
    from boreas.collectors import energy_charts, entsoe, markets, netztransparenz, open_meteo

    async def go():
        await db.init_db()
        for mod, name in ((entsoe, "entsoe"), (energy_charts, "energy_charts"),
                          (open_meteo, "open_meteo"), (netztransparenz, "netztransparenz"),
                          (markets, "markets")):
            try:
                await mod.collect()
            except Exception as e:  # noqa: BLE001
                typer.echo(f"{name} failed: {e}")
        await db.close_pool()

    _run(go())


@app.command()
def features():
    """Compute and store one FeatureFrame, print the headline."""
    from boreas import db
    from boreas.features import engine

    async def go():
        await db.init_db()
        frame = await engine.run_cycle()
        typer.echo(frame.headline())
        await db.close_pool()

    _run(go())


@app.command()
def cycle(plain: bool = typer.Option(False, help="skip LangGraph checkpointing")):
    """One full society cycle: features -> sentinel -> analyst -> risk -> executor."""
    from boreas import db
    from boreas.agents import graph
    from boreas.features import engine

    async def go():
        await db.init_db()
        frame = await engine.run_cycle()
        state = await (graph.run_cycle_plain(frame) if plain else graph.run_cycle(frame))
        typer.echo(f"verdict={state.get('verdict')} thesis_id={state.get('thesis_id')}")
        await db.close_pool()

    _run(go())


@app.command()
def baseline(date_s: str = typer.Option("", "--date", help="delivery date, default tomorrow")):
    """Fit the rolling baseline and predict B_h for a delivery day."""
    from boreas import db
    from boreas.baseline import model

    async def go():
        await db.init_db()
        day = (datetime.fromisoformat(date_s).date() if date_s
               else (datetime.now(UTC) + timedelta(days=1)).date())
        preds = await model.predict_day(day)
        typer.echo(f"{len(preds)} quarter-hours predicted for {day}")
        await db.close_pool()

    _run(go())


@app.command()
def settle():
    """Settle due paper orders and run the Reflector."""
    from boreas import db
    from boreas.agents import reflector
    from boreas.trading.book import settle_due_orders

    async def go():
        await db.init_db()
        legs = await settle_due_orders()
        n = await reflector.reflect_settled()
        typer.echo(f"settled {len(legs)} legs, reflected on {n} theses")
        await db.close_pool()

    _run(go())


@app.command()
def report():
    """Regenerate the static JSON for the track-record site."""
    from boreas import db
    from boreas.reporting import reporter

    async def go():
        await db.init_db()
        summary = await reporter.export_all()
        typer.echo(f"P&L {summary['total_pnl_eur']} EUR over {summary['n_theses_settled']} theses")
        await db.close_pool()

    _run(go())


@app.command()
def approve_playbook(version: int):
    """Approve a structural playbook change (PR-style)."""
    from boreas import db
    from boreas.agents import playbook

    async def go():
        await db.init_db()
        await playbook.approve(version)
        typer.echo(f"playbook v{version} approved")
        await db.close_pool()

    _run(go())


@app.command()
def run():
    """Run the full scheduler (collectors + agents + reporting), forever."""
    from boreas import scheduler

    _run(scheduler.main())


if __name__ == "__main__":
    app()
