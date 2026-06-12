from boreas.trading.limits import LIMITS, RiskLimits, check_thesis, kelly_size_mw


def test_kelly_zero_when_no_edge():
    assert kelly_size_mw(confidence=0.5, expected_move_eur=5.0) == 0.0


def test_kelly_positive_with_edge():
    q = kelly_size_mw(confidence=0.7, expected_move_eur=30.0)
    assert 0 < q <= LIMITS.max_mw_per_qh


def test_kelly_capped():
    q = kelly_size_mw(confidence=0.99, expected_move_eur=500.0)
    assert q <= LIMITS.max_mw_per_qh


def test_kelly_scales_with_confidence():
    lo = kelly_size_mw(0.6, 40.0)
    hi = kelly_size_mw(0.9, 40.0)
    assert hi > lo


def test_daily_stop_blocks():
    ok, reason = check_thesis(10, 4, 0, 0, realized_pnl_today=-99999)
    assert not ok and "stop" in reason


def test_concurrent_theses_blocks():
    ok, reason = check_thesis(10, 4, LIMITS.max_concurrent_theses, 0, 0)
    assert not ok and "concurrent" in reason


def test_gross_cap_blocks():
    limits = RiskLimits(max_gross_mw_day=100)
    ok, reason = check_thesis(20, 10, 0, 0, 0, limits=limits)  # 200 MW gross > 100
    assert not ok and "gross" in reason


def test_zero_qty_blocks():
    ok, reason = check_thesis(0, 4, 0, 0, 0)
    assert not ok


def test_clean_thesis_passes():
    ok, reason = check_thesis(10, 8, 1, 100, 0)
    assert ok
