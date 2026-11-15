"""Lake-flood hazard: priority-flood, zone/arrival rules, and a full flood scenario on the synthetic city."""
import math

import numpy as np
import pytest
import shapely

from contracts.engine_api import FloodStep, ScenarioParams, ScenarioResult
from engine import assumptions as A
from engine.decisions import EVACUATE, SHELTER
from engine.flood import build_flood_hazard, priority_flood
from engine.scenario import run_scenario
from engine.synthetic import center_release


def test_priority_flood_needs_to_overtop_a_ridge():
    # lake | 1 m | 3 m ridge | 0.5 m hollow behind it | 1 m
    elev = np.array([[0.0, 1.0, 3.0, 0.5, 1.0]])
    lake = np.array([[True, False, False, False, False]])
    lvl = priority_flood(elev, lake, np.zeros_like(lake))
    assert lvl[0, 1] == 1.0
    assert lvl[0, 2] == 3.0
    assert lvl[0, 3] == 3.0          # the hollow is low, but water only gets there over the ridge
    assert lvl[0, 4] == 3.0


def test_priority_flood_blocked_cells_and_unreachable():
    elev = np.zeros((3, 3))
    seeds = np.zeros((3, 3), bool)
    seeds[0, 0] = True
    wall = np.zeros((3, 3), bool)
    wall[:, 1] = True                # a column water can't cross (the other lake / a dam)
    lvl = priority_flood(elev, seeds, wall)
    assert lvl[0, 0] == -np.inf                      # the lake itself
    assert (lvl[1:, 0] == 0.0).all()                 # reachable land on the lake's side
    assert (lvl[:, 2] == np.inf).all()               # behind the wall: never


def test_grid_loaded(net):
    assert net.flood is not None
    assert set(net.flood.rise) == {"mendota", "monona", "both"}
    assert all(net.flood.lake_wkt[k] for k in ("mendota", "monona", "both"))


def test_zone_and_arrival_rules(net):
    hz = build_flood_hazard(net, "both", 2.0, 6.0)
    xs = net.blocks["x"].to_numpy()
    ys = net.blocks["y"].to_numpy()
    need = hz.need(xs, ys)
    np.testing.assert_array_equal(hz.in_zone(xs, ys), need <= 2.0)
    arr = hz.arrival_s(xs, ys)
    inside = need <= 2.0
    assert inside.any() and (~inside).any()
    np.testing.assert_allclose(arr[inside], 6 * 3600 * need[inside] / 2.0)
    assert np.isnan(arr[~inside]).all()
    # scalar in → scalar out, like the chemical hazard
    assert isinstance(hz.in_zone(float(xs[0]), float(ys[0])), (bool, np.bool_))
    assert np.ndim(hz.arrival_s(float(xs[0]), float(ys[0]))) == 0


def test_more_rise_floods_more(net):
    xs, ys = net.blocks["x"].to_numpy(), net.blocks["y"].to_numpy()
    small = build_flood_hazard(net, "both", 1.0, 6.0).in_zone(xs, ys)
    big = build_flood_hazard(net, "both", 3.0, 6.0).in_zone(xs, ys)
    assert big.sum() > small.sum() and (big | ~small).all()      # superset


def test_sources_differ(net):
    xs, ys = net.blocks["x"].to_numpy(), net.blocks["y"].to_numpy()
    men = build_flood_hazard(net, "mendota", 2.0, 6.0).in_zone(xs, ys)
    mon = build_flood_hazard(net, "monona", 2.0, 6.0).in_zone(xs, ys)
    both = build_flood_hazard(net, "both", 2.0, 6.0).in_zone(xs, ys)
    assert (men != mon).any()
    np.testing.assert_array_equal(both, men | mon)


def test_low_channel_floods_first(net):
    # synthetic ground has a 1 m dip along the arterial column: those cells need less rise than neighbours
    hz = build_flood_hazard(net, "monona", 3.0, 6.0)
    from engine.synthetic import ARTERIAL_COL, DLAT, DLON, LAT0, LON0
    from engine.network import to_metric
    x_mid, y = to_metric(LON0 + ARTERIAL_COL * DLON, LAT0 + 2 * DLAT)
    x_side, _ = to_metric(LON0 + (ARTERIAL_COL - 2) * DLON, LAT0 + 2 * DLAT)
    assert hz.need(x_mid, y) < hz.need(x_side, y)


@pytest.fixture(scope="module")
def flood_result(net) -> ScenarioResult:
    lon, lat = center_release()
    p = ScenarioParams(release_lon=lon, release_lat=lat, hazard="flood", flood_source="both",
                       flood_rise_m=2.5, flood_peak_h=1.0, time_of_day="night", bus_count=10)
    return run_scenario(p, net)


def test_flood_scenario_contract(flood_result):
    r = flood_result
    assert r.isolation_zone_wkt == ""
    assert not shapely.from_wkt(r.protect_zone_wkt).is_empty
    assert not shapely.from_wkt(r.flood_source_wkt).is_empty
    assert len(r.flood_steps) == A.FLOOD_STEPS and all(isinstance(s, FloodStep) for s in r.flood_steps)
    ts = [s.t_s for s in r.flood_steps]
    assert ts == sorted(ts) and math.isclose(ts[-1], 3600.0)
    assert math.isclose(r.flood_steps[-1].rise_m, 2.5)


def test_flood_decisions(flood_result):
    blocks = flood_result.blocks
    assert {b.decision for b in blocks} >= {EVACUATE, "outside"}
    for b in blocks:
        if b.decision == "outside":
            assert b.plume_arrival_s is None
        else:
            assert b.plume_arrival_s is not None and b.plume_arrival_s <= 3600.0 + 1e-6
        if b.decision == SHELTER and b.est_exit_time_s is not None:
            assert b.est_exit_time_s >= b.plume_arrival_s - 1e-6     # couldn't beat the water


def test_flood_buses_beat_the_water(flood_result):
    for r in flood_result.buses:
        for t, dl in zip(r.arrival_s, r.deadline_s):
            if dl is not None:
                assert t <= dl + 1e-6


def test_chemical_unchanged_by_default(net):
    lon, lat = center_release()
    r = run_scenario(ScenarioParams(release_lon=lon, release_lat=lat), net)
    assert r.isolation_zone_wkt and r.flood_steps == [] and r.flood_source_wkt == ""
