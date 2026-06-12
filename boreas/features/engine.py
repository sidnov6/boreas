"""Feature engine: every 15 minutes, compute a typed FeatureFrame from the canonical store."""
from __future__ import annotations

import json
import logging
import statistics
from datetime import UTC, datetime, timedelta

import numpy as np

from boreas import db
from boreas.features.frame import Divergence, FeatureFrame, ForecastError
from boreas.features.power_curve import fleet_generation_mw, solar_generation_mw
from boreas.mastr.sites import SITES

log = logging.getLogger("boreas.features")


def error_stats(actual: dict[datetime, float], forecast: dict[datetime, float],
                now: datetime) -> ForecastError:
    """Trailing forecast-error stats over the last 6h (actual - forecast)."""
    common = sorted(set(actual) & set(forecast))
    recent = [ts for ts in common if now - timedelta(hours=6) <= ts <= now]
    if not recent:
        return ForecastError()
    errs = [(ts, actual[ts] - forecast[ts]) for ts in recent]
    vals = [e for _, e in errs]
    last3h = [e for ts, e in errs if ts >= now - timedelta(hours=3)]
    trend = None
    if len(errs) >= 3:
        xs = np.array([(ts - errs[0][0]).total_seconds() / 3600.0 for ts, _ in errs])
        ys = np.array(vals)
        trend = float(np.polyfit(xs, ys, 1)[0])
    return ForecastError(
        current_mw=vals[-1],
        mean_3h_mw=statistics.fmean(last3h) if last3h else None,
        mean_6h_mw=statistics.fmean(vals),
        trend_mw_per_h=trend,
    )


def ramp_coincidence_mw_per_h(solar_fc: dict[datetime, float], wind_fc: dict[datetime, float],
                              now: datetime, horizon_h: int = 4) -> float | None:
    """Max coincident absolute ramp (solar drop-off meeting a wind ramp) over the next hours."""
    worst = None
    for h in range(horizon_h):
        t0, t1 = now + timedelta(hours=h), now + timedelta(hours=h + 1)
        s0, s1 = _nearest(solar_fc, t0), _nearest(solar_fc, t1)
        w0, w1 = _nearest(wind_fc, t0), _nearest(wind_fc, t1)
        if None in (s0, s1, w0, w1):
            continue
        combined = abs((s1 - s0) + (w1 - w0))
        worst = combined if worst is None else max(worst, combined)
    return worst


def _nearest(series: dict[datetime, float], ts: datetime, tol_min: int = 31) -> float | None:
    if not series:
        return None
    best = min(series, key=lambda t: abs((t - ts).total_seconds()))
    if abs((best - ts).total_seconds()) > tol_min * 60:
        return None
    return series[best]


def zscore(value: float, history: list[float]) -> float | None:
    if len(history) < 10:
        return None
    sd = statistics.pstdev(history)
    if sd < 1e-9:
        return None
    return (value - statistics.fmean(history)) / sd


async def compute_frame(now: datetime | None = None) -> FeatureFrame:
    now = (now or datetime.now(UTC)).replace(second=0, microsecond=0)
    past6 = now - timedelta(hours=6)
    fwd36 = now + timedelta(hours=36)

    load_a = await db.latest_series("load.actual", past6, now)
    load_f = await db.latest_series("load.forecast", past6, fwd36)
    solar_a = await db.latest_series("solar.actual", past6, now)
    solar_f = await db.latest_series("solar.forecast", past6, fwd36)
    won_a = await db.latest_series("wind_onshore.actual", past6, now)
    won_f = await db.latest_series("wind_onshore.forecast", past6, fwd36)
    woff_a = await db.latest_series("wind_offshore.actual", past6, now)
    woff_f = await db.latest_series("wind_offshore.forecast", past6, fwd36)

    wind_a = _sum_series(won_a, woff_a)
    wind_f = _sum_series(won_f, woff_f)

    frame = FeatureFrame(ts=now)
    frame.load_error = error_stats(load_a, load_f, now)
    frame.solar_error = error_stats(solar_a, solar_f, now)
    frame.wind_error = error_stats(wind_a, wind_f, now)

    l_now, w_now, s_now = _nearest(load_a, now), _nearest(wind_a, now), _nearest(solar_a, now)
    if None not in (l_now, w_now, s_now):
        frame.residual_load_mw = l_now - w_now - s_now
    l_fc, w_fc, s_fc = _nearest(load_f, now), _nearest(wind_f, now), _nearest(solar_f, now)
    if None not in (l_fc, w_fc, s_fc):
        frame.residual_load_forecast_mw = l_fc - w_fc - s_fc

    frame.ramp_coincidence = ramp_coincidence_mw_per_h(solar_f, wind_f, now)

    # --- The divergence signal: BOREAS nowcast vs TSO forecast, day-ahead horizon ---
    target = (now + timedelta(hours=24)).replace(minute=0)
    wind_by_site, ghi_by_site = {}, {}
    for site in SITES:
        w = await db.latest_series(f"meteo.wind100m.{site.id}", target, target + timedelta(hours=1))
        g = await db.latest_series(f"meteo.ghi.{site.id}", target, target + timedelta(hours=1))
        if w:
            wind_by_site[site.id] = next(iter(w.values()))
        if g:
            ghi_by_site[site.id] = next(iter(g.values()))

    if wind_by_site:
        cap_on = {s.id: s.wind_onshore_gw for s in SITES}
        cap_off = {s.id: s.wind_offshore_gw for s in SITES}
        boreas_wind = fleet_generation_mw(wind_by_site, cap_on) + fleet_generation_mw(wind_by_site, cap_off)
        tso_wind = _nearest(wind_f, target, tol_min=61)
        if tso_wind is not None:
            delta = boreas_wind - tso_wind
            hist = await _divergence_history("wind")
            frame.wind_divergence = Divergence(
                boreas_mw=boreas_wind, tso_mw=tso_wind, delta_mw=delta, zscore=zscore(delta, hist))
    if ghi_by_site:
        cap_pv = {s.id: s.solar_gw for s in SITES}
        boreas_solar = solar_generation_mw(ghi_by_site, cap_pv)
        tso_solar = _nearest(solar_f, target, tol_min=61)
        if tso_solar is not None:
            delta = boreas_solar - tso_solar
            hist = await _divergence_history("solar")
            frame.solar_divergence = Divergence(
                boreas_mw=boreas_solar, tso_mw=tso_solar, delta_mw=delta, zscore=zscore(delta, hist))

    nrv = await db.latest_series("nrv_saldo", now - timedelta(hours=2), now + timedelta(minutes=1))
    if nrv:
        frame.nrv_saldo_mw = nrv[max(nrv)]
    da = await db.latest_series("price.da", now - timedelta(minutes=30), now + timedelta(minutes=30))
    if da:
        frame.da_price_eur = next(iter(da.values()))

    ttf = await db.latest_series("ttf.close", now - timedelta(days=7), now + timedelta(days=1))
    eua = await db.latest_series("eua.close", now - timedelta(days=7), now + timedelta(days=1))
    if ttf:
        frame.ttf_eur = ttf[max(ttf)]
    if eua:
        frame.eua_eur = eua[max(eua)]
    if frame.ttf_eur is not None and frame.residual_load_mw is not None:
        # Gas on the margin when residual load is high; steep stack amplifies forecast errors.
        frame.merit_order_steep = frame.residual_load_mw > 35000 and frame.ttf_eur > 25

    return frame


async def _divergence_history(kind: str, days: int = 30) -> list[float]:
    p = await db.pool()
    recs = await p.fetch(
        """
        SELECT (frame -> ($1 || '_divergence') ->> 'delta_mw')::float AS d
        FROM feature_frames
        WHERE ts > now() - ($2 || ' days')::interval
          AND frame -> ($1 || '_divergence') ->> 'delta_mw' IS NOT NULL
        ORDER BY ts
        """,
        kind, str(days),
    )
    return [r["d"] for r in recs if r["d"] is not None]


def _sum_series(a: dict[datetime, float], b: dict[datetime, float]) -> dict[datetime, float]:
    out = dict(a)
    for ts, v in b.items():
        out[ts] = out.get(ts, 0.0) + v
    return out


async def run_cycle() -> FeatureFrame:
    frame = await compute_frame()
    p = await db.pool()
    await p.execute(
        """
        INSERT INTO feature_frames (ts, frame) VALUES ($1, $2::jsonb)
        ON CONFLICT (ts) DO UPDATE SET frame = EXCLUDED.frame
        """,
        frame.ts, json.dumps(frame.model_dump(mode="json")),
    )
    await db.notify("feature_frame", {"ts": frame.ts.isoformat(), "headline": frame.headline()})
    log.info("frame %s: %s", frame.ts, frame.headline())
    return frame
