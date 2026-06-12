from boreas.features.power_curve import capacity_factor, fleet_generation_mw, solar_generation_mw


def test_below_cut_in_is_zero():
    assert capacity_factor(0.0) == 0.0
    assert capacity_factor(2.9) == 0.0


def test_storm_shutdown():
    assert capacity_factor(25.0) == 0.0
    assert capacity_factor(30.0) == 0.0


def test_monotonic_in_operating_range():
    speeds = [4, 6, 8, 10, 12, 14]
    cfs = [capacity_factor(s) for s in speeds]
    assert all(b > a for a, b in zip(cfs, cfs[1:]))


def test_near_rated_close_to_one():
    assert capacity_factor(18.0) > 0.95


def test_fleet_generation_weighted():
    wind = {"a": 10.0, "b": 0.0}
    caps = {"a": 1.0, "b": 5.0}  # site b has 5 GW but no wind
    gen = fleet_generation_mw(wind, caps)
    assert 0 < gen < 1000  # only site a (1 GW) contributes
    assert gen == capacity_factor(10.0) * 1000


def test_fleet_ignores_missing_sites():
    assert fleet_generation_mw({}, {"a": 3.0}) == 0.0


def test_solar_conversion():
    gen = solar_generation_mw({"x": 1000.0}, {"x": 2.0}, performance_ratio=0.85)
    assert gen == 0.85 * 2000.0
    assert solar_generation_mw({"x": 0.0}, {"x": 2.0}) == 0.0
