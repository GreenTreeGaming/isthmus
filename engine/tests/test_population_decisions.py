import numpy as np
import pandas as pd
import pytest

from engine import assumptions as A
from engine.decisions import EVACUATE, OUTSIDE, SHELTER, decide, estimate_exit_s
from engine.population import facility_need_bus, split_population


def _blocks(**kw):
    base = dict(block_id=["b1"], node_id=[1], pop_night=[100.0], pop_day=[100.0], pop_gameday=[100.0],
                households=[40.0], zero_vehicle_share=[0.25], disability_share=[0.10], age65_share=[0.20])
    base.update(kw)
    return pd.DataFrame(base)


def test_people_conserved():
    s = split_population(_blocks(), "night").iloc[0]
    assert s.driver_people + s.walkers + s.need_bus == pytest.approx(100.0)


def test_need_bus_formula():
    s = split_population(_blocks(), "night").iloc[0]
    carfree = 100 * 0.25
    assert s.need_bus == pytest.approx(carfree * (0.10 + A.AGE65_NEED_BUS_WEIGHT * 0.20))


def test_vehicles_per_household():
    s = split_population(_blocks(), "night").iloc[0]
    # 40 households, 25% car-free → 30 car households × 1 car
    assert s.vehicles == pytest.approx(30 * A.VEHICLES_PER_HOUSEHOLD)


def test_visitors_add_vehicles_on_gameday():
    night = split_population(_blocks(pop_gameday=[10_100.0]), "night").iloc[0]
    game = split_population(_blocks(pop_gameday=[10_100.0]), "gameday").iloc[0]
    expected_extra = 10_000 * A.VISITOR_DRIVE_SHARE / A.VISITOR_OCCUPANCY
    assert game.vehicles - night.vehicles == pytest.approx(expected_extra)
    assert game.need_bus == pytest.approx(night.need_bus)   # visitors don't need buses


def test_daytime_fewer_residents():
    s = split_population(_blocks(pop_day=[50.0]), "day").iloc[0]
    assert s.pop == 50
    assert s.driver_people + s.walkers + s.need_bus == pytest.approx(50.0)


def test_nursing_home_residents_need_bus():
    f = pd.DataFrame({"facility_id": ["a", "b"], "type": ["nursing_home", "hospital"], "residents": [80, 200]})
    nh = facility_need_bus(f)
    assert list(nh["facility_id"]) == ["a"] and nh["need_bus"].sum() == 80


def test_decide():
    in_zone = np.array([True, True, False, True])
    arrival = np.array([100.0, 5000.0, np.nan, 5000.0])
    est = estimate_exit_s(np.array([200.0, 200.0, 200.0, np.inf]))
    d = decide(in_zone, arrival, est)
    assert list(d) == [SHELTER, EVACUATE, OUTSIDE, SHELTER]
