import json
from collections import Counter
from dataclasses import asdict

import pytest
import shapely

from contracts.engine_api import ScenarioParams, ScenarioResult
from engine import assumptions as A
from engine import run_scenario
from engine.scenario import run_with_diagnostics
from engine.synthetic import center_release


@pytest.fixture(autouse=True)
def fast_buses(monkeypatch):
    monkeypatch.setattr(A, "BUS_SOLVER_TIME_LIMIT_S", 0.2)


def _params(**kw):
    lon, lat = center_release()
    base = dict(release_lon=lon, release_lat=lat, wind_from_deg=225.0, wind_speed_mps=1.0, time_of_day="gameday")
    base.update(kw)
    return ScenarioParams(**base)


@pytest.fixture(scope="module")
def result(net):
    return run_with_diagnostics(_params(), net)


def test_contract_types(result):
    r, _ = result
    assert isinstance(r, ScenarioResult)
    json.dumps(asdict(r))                      # must be JSON-serializable for the backend
    assert shapely.from_wkt(r.isolation_zone_wkt).is_valid
    assert shapely.from_wkt(r.protect_zone_wkt).is_valid


def test_has_all_three_decisions(result):
    r, _ = result
    c = Counter(b.decision for b in r.blocks)
    assert c["evacuate"] > 0 and c["shelter"] > 0 and c["outside"] > 0


def test_waves_only_for_evacuees(result):
    r, _ = result
    for b in r.blocks:
        assert (b.wave is not None) == (b.decision == "evacuate")
        if b.decision == "outside":
            assert b.plume_arrival_s is None


def test_shelter_means_plume_beats_exit(result):
    r, _ = result
    for b in r.blocks:
        if b.decision == "shelter" and b.est_exit_time_s is not None:
            assert b.plume_arrival_s <= b.est_exit_time_s
        if b.decision == "evacuate":
            assert b.est_exit_time_s < b.plume_arrival_s


def test_edges_and_bottlenecks_consistent(result, net):
    r, _ = result
    ids = {e.edge_id for e in r.edges}
    assert set(r.summary.bottleneck_edge_ids) <= ids
    assert all(e.edge_id in net.edge_uv for e in r.edges)
    assert set(r.load_timeline) <= ids


def test_buses_valid(result):
    r, _ = result
    p = r.params
    for b in r.buses:
        assert b.stops[0] == "garage_main" and b.stops[-1] == "shelter_east"
        assert max(b.load) <= p.bus_capacity
        assert b.arrival_s == sorted(b.arrival_s)
        assert len(b.stops) == len(b.arrival_s) == len(b.load)
    assert 0 <= r.summary.need_bus_unserved <= r.summary.need_bus_total


def test_sim_close_to_flow_plan(result):
    r, d = result
    # sim includes mobilization + staggered waves, so it should be later but the same order of magnitude
    assert d.flow_clearance_s <= d.sim_clearance_s + A.SIM_STEP_S
    assert d.sim_clearance_s < 4 * d.flow_clearance_s + A.MOBILIZATION_S + 3 * A.WAVE_INTERVAL_S


def test_sim_clearance_in_summary(result):
    r, d = result
    assert r.summary.sim_clearance_s == d.sim_clearance_s > 0


def test_runtime_under_5s(result):
    r, _ = result
    assert r.summary.runtime_ms < 5000


def test_lower_compliance_fewer_vehicles(net):
    _, hi = run_with_diagnostics(_params(compliance=1.0), net)
    _, lo = run_with_diagnostics(_params(compliance=0.6), net)
    assert lo.vehicles < hi.vehicles


def test_closed_edge_not_used(net, result):
    r, _ = result
    victim = r.summary.bottleneck_edge_ids[0]
    r2 = run_scenario(_params(closed_edge_ids=(victim,)), net)
    assert victim not in {e.edge_id for e in r2.edges}


def test_upwind_release_far_away_is_all_outside(net):
    # Wind blowing the gas off the grid's west edge: nobody downwind on the map.
    lon, lat = center_release()
    r = run_scenario(_params(release_lon=lon - 0.012, wind_from_deg=90.0, spill_size="small"), net)
    assert r.summary.people_evacuating >= 0
    assert sum(b.decision != "outside" for b in r.blocks) < len(r.blocks) / 4


def test_fast_wind_more_sheltering(net):
    slow = run_scenario(_params(wind_speed_mps=0.6), net)
    fast = run_scenario(_params(wind_speed_mps=6.0), net)
    assert fast.summary.people_sheltering > slow.summary.people_sheltering


def test_shelter_is_outside_danger_area(net):
    import numpy as np
    from engine.hazard import build_hazard
    r = run_scenario(_params(), net)
    p = r.params
    hz = build_hazard(net, p.release_lon, p.release_lat, p.chemical, p.spill_size, p.time_of_day,
                      p.wind_from_deg, p.wind_speed_mps)
    d = net.depots.set_index("depot_id")
    for b in r.buses:
        sid = b.stops[-1]
        if sid in d.index and d.at[sid, "kind"] == "shelter":
            others = net.depots[net.depots["kind"] == "shelter"]
            if (~hz.in_region(others["x"].to_numpy(), others["y"].to_numpy())).any():
                assert not hz.in_region(d.at[sid, "x"], d.at[sid, "y"])


def test_no_vehicles_assigned_to_undrivable_nodes(net):
    """Regression: a walk-out block whose fractional car sat on a node with no drivable exit made flow infeasible."""
    from engine.scenario import run_with_diagnostics
    for wf in (0.0, 90.0, 180.0, 270.0):
        r, d = run_with_diagnostics(_params(wind_from_deg=wf, wind_speed_mps=4.0), net)
        assert r.summary.clearance_time_s >= 0
