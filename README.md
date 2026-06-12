# BOREAS

An autonomous agent that paper-trades the German power market, in public.

**Live track record:** [sidnov6-boreas.static.hf.space](https://sidnov6-boreas.static.hf.space) · **Source:** [github.com/sidnov6/boreas](https://github.com/sidnov6/boreas)

BOREAS builds its own wind and solar nowcast from DWD ICON-D2 weather fields (Open-Meteo),
compares it with the TSO forecasts behind the EPEX day-ahead auction (ENTSO-E Transparency),
and takes paper positions on 15-minute products when the two disagree — then publishes every
thesis, settlement and playbook revision to a static track-record site.

## Why this design

Real-time EPEX intraday continuous prices are licensed and expensive, so BOREAS trades two
precisely defined paper conventions instead:

- **v1 — DA curve**: before the 12:00 CET day-ahead gate, submit a position vector `q_h` over
  tomorrow's 96 quarter-hours. `P&L_h = q_h × (P_DA_h − B_h) × 0.25`, where `B_h` is a rolling
  90-day regression from TSO-forecast residual load to price — a competent baseline, not
  persistence. Beating it means genuine forecast edge.
- **v2 — DA–reBAP spread**: intraday, long/short the spread between the imbalance price (reBAP)
  and DA for remaining quarter-hours, using live NRV-Saldo as the decision signal; settles on
  preliminary reBAP when it publishes (verify the publication lag in week one).

## Architecture

```
collectors (httpx + APScheduler, 15-min cadence)
  ENTSO-E · Energy-Charts · Open-Meteo/ICON-D2 · Netztransparenz · TTF/EUA
        │  canonical rows, forecast vintages never overwritten → fully replayable
        ▼
TimescaleDB (one database: observations, features, theses, book, playbook, runs)
        │  LISTEN/NOTIFY
        ▼
feature engine (15-min FeatureFrame: forecast errors, residual load, ramp coincidence,
                merit-order regime, divergence z-score vs BOREAS's own power-curve nowcast)
        ▼
agent society (LangGraph, checkpointed to Postgres)
  Sentinel (rules + Haiku gate, ~90% of cycles end here)
  → Analyst (Sonnet: analog days, playbook, structured Thesis with falsifier)
  → Risk Officer (capped fractional Kelly inside hard-coded limits; LLM can veto, never raise)
  → Executor (deterministic: paper orders with full lineage + Telegram alert)
  Reflector (on settlement: attribution, journal, playbook diffs — structural ones wait for approval)
        ▼
reporter (nightly JSON) → Next.js static track-record site
```

## Quick start

```bash
# 1. Infrastructure
make db            # TimescaleDB via docker compose (host port 5433)
make install       # python venv + deps
cp .env.example .env   # fill in keys as you get them

# 2. Schema + first data
.venv/bin/boreas init-db
.venv/bin/boreas collect       # all collectors once (Energy-Charts + Open-Meteo work with zero keys)
.venv/bin/boreas features      # one FeatureFrame
.venv/bin/boreas backfill --days 365   # ENTSO-E history (needs ENTSOE_API_KEY)

# 3. The loop
.venv/bin/boreas cycle         # one society cycle (needs ANTHROPIC_API_KEY)
.venv/bin/boreas baseline      # fit + predict B_h for tomorrow
.venv/bin/boreas settle        # settle due orders + run the Reflector
.venv/bin/boreas report        # regenerate site JSON
.venv/bin/boreas run           # everything, forever (APScheduler)

# 4. The site
cd site && npm install && npm run dev
```

## Data sources

| Source | What | Auth |
|---|---|---|
| ENTSO-E Transparency | load/generation actuals + TSO forecasts + DA prices (A65/A75/A69/A44) | free token (email helpdesk to enable API) |
| Energy-Charts (Fraunhofer ISE) | same German market data, independent pipe — redundancy layer | none |
| Open-Meteo (DWD ICON-D2) | 100m/120m wind + irradiance at 25 capacity-weighted grid points | none |
| Netztransparenz | NRV-Saldo (live imbalance), reBAP | free client-credentials registration |
| Yahoo Finance | TTF gas + EUA carbon (regime context, daily) | none |
| MaStR | regional installed capacity (seeded in `boreas/mastr/sites.py`, refresh monthly) | none |

Forecast vintages are never overwritten — every TSO revision and ICON run is a new row keyed by
`(series_id, zone, ts_event, ts_published, model_run, source)`. Any past day can be replayed
exactly as the agents saw it live, which gives free backtesting and "what would playbook v3 have
done in March" comparisons.

## Risk limits (in code, not in prompts)

`boreas/trading/limits.py`: max 25 MW per quarter-hour, 600 MW gross per day, max 3 concurrent
theses, −2,000 € daily stop, 0.25 fractional Kelly. The LLM only argues within them — its
commentary can veto a trade, never raise the size.

## Operations

- Every collector cycle pings healthchecks.io (`HEALTHCHECKS_URL`) — dead collectors page you
  instead of dying silently.
- Telegram alerts on every executed thesis, settlement and structural playbook proposal.
- Structural playbook changes are PR-style: `boreas approve-playbook <version>`.

## Tests

```bash
make test   # pure-function suite: power curve, P&L, Kelly/limits, features, baseline, analogs
```
