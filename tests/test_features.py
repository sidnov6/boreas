from datetime import UTC, datetime, timedelta

from boreas.baseline.model import QhModel, fit_qh_models
from boreas.features.analogs import analog_distance, top_analogs
from boreas.features.engine import error_stats, ramp_coincidence_mw_per_h, zscore
from boreas.features.frame import FeatureFrame

NOW = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)


def _hourly(start, values):
    return {start + timedelta(hours=i): v for i, v in enumerate(values)}


def test_error_stats_direction():
    actual = _hourly(NOW - timedelta(hours=5), [100, 200, 300, 400, 500, 600])
    forecast = _hourly(NOW - timedelta(hours=5), [100, 100, 100, 100, 100, 100])
    es = error_stats(actual, forecast, NOW)
    assert es.current_mw == 500
    assert es.trend_mw_per_h is not None and es.trend_mw_per_h > 90


def test_error_stats_empty():
    es = error_stats({}, {}, NOW)
    assert es.current_mw is None


def test_ramp_coincidence_detects_evening_setup():
    # solar collapsing while wind ramps: coincident |ramp| should be large
    solar = _hourly(NOW, [8000, 5000, 2000, 500, 0])
    wind = _hourly(NOW, [10000, 12000, 14000, 16000, 18000])
    ramp = ramp_coincidence_mw_per_h(solar, wind, NOW)
    assert ramp is not None and ramp >= 1000


def test_zscore_needs_history():
    assert zscore(1.0, [1.0] * 5) is None
    hist = [0.0] * 15 + [1.0] * 15
    z = zscore(10.0, hist)
    assert z is not None and z > 5


def test_frame_hash_is_stable():
    f1 = FeatureFrame(ts=NOW, residual_load_mw=42000)
    f2 = FeatureFrame(ts=NOW, residual_load_mw=42000)
    f3 = FeatureFrame(ts=NOW, residual_load_mw=43000)
    assert f1.hash() == f2.hash() != f3.hash()
    assert "resid_load=42000" in f1.headline()


def test_analog_distance_prefers_same_shape():
    base = [10, 20, 30, 40, 30, 20]
    same_scaled = [100, 200, 300, 400, 300, 200]  # identical shape, different level
    different = [40, 30, 20, 10, 20, 30]
    assert analog_distance(base, same_scaled) < analog_distance(base, different)


def test_top_analogs_orders_by_distance():
    target = [1, 2, 3, 4]
    cands = {"good": [10, 20, 30, 40], "bad": [4, 3, 2, 1], "ok": [1, 2, 3, 3]}
    ranked = top_analogs(target, cands, k=3)
    assert ranked[0][0] == "good"


def test_baseline_fit_and_fallback():
    # qh 0 has plenty of samples; qh 1 sparse -> pooled fallback
    samples = {0: [(30000 + i * 100, 50 + i) for i in range(30)], 1: [(40000, 80)]}
    models = fit_qh_models(samples, min_samples=20)
    assert 0 in models and 1 in models
    assert models[0].predict(33000) > models[0].predict(30000)  # positive slope


def test_qh_model_predicts_linear():
    m = QhModel(intercept=10.0, slope=0.001)
    assert m.predict(40000) == 50.0
