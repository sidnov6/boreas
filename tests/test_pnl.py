import pytest

from boreas.trading.pnl import pnl_da_curve, pnl_da_rebap_spread, settle


def test_da_curve_long_wins_when_price_above_baseline():
    # long 10 MW, DA clears 20 EUR over baseline, one quarter-hour
    assert pnl_da_curve(10.0, 120.0, 100.0) == pytest.approx(10 * 20 * 0.25)


def test_da_curve_short_wins_when_price_below_baseline():
    assert pnl_da_curve(-10.0, 80.0, 100.0) == pytest.approx(50.0)


def test_da_curve_symmetry():
    assert pnl_da_curve(5.0, 90.0, 100.0) == -pnl_da_curve(-5.0, 90.0, 100.0)


def test_rebap_spread_long():
    # long the spread: profits when reBAP settles above DA
    assert pnl_da_rebap_spread(8.0, 250.0, 150.0) == pytest.approx(8 * 100 * 0.25)


def test_rebap_spread_short_loses_when_rebap_spikes():
    assert pnl_da_rebap_spread(-8.0, 250.0, 150.0) == pytest.approx(-200.0)


def test_settle_dispatch():
    assert settle("da_curve", 10.0, 100.0, 120.0) == pnl_da_curve(10.0, 120.0, 100.0)
    assert settle("da_rebap_spread", 10.0, 150.0, 250.0) == pnl_da_rebap_spread(10.0, 250.0, 150.0)


def test_settle_unknown_strategy():
    with pytest.raises(ValueError):
        settle("yolo", 1.0, 1.0, 1.0)
