import numpy as np
import pytest

from engine import assumptions as A
from engine.flow import solve_flow


def _arr(*xs):
    return np.array(xs, dtype=float)


def test_single_road_units():
    # 0 → 1 (exit). 600 veh/h road, 300 vehicles → needs 30 minutes of capacity.
    r = solve_flow(2, np.array([0]), np.array([1]), _arr(600), _arr(60), _arr(60), [1], {0: 300})
    assert r.clearance_cap_s == pytest.approx(1800, abs=A.CLEARANCE_TOLERANCE_S + 1)
    assert r.clearance_s == pytest.approx(r.clearance_cap_s + 60)
    assert r.arc_flow[0] == 300
    assert r.bottleneck_arcs == [0]


def test_parallel_roads_halve_time():
    one = solve_flow(3, np.array([0]), np.array([2]), _arr(600), _arr(60), _arr(60), [2], {0: 600})
    two = solve_flow(3, np.array([0, 0, 1]), np.array([2, 1, 2]), _arr(600, 600, 600), _arr(60, 30, 30),
                     _arr(60, 30, 30), [2], {0: 600})
    assert two.clearance_cap_s == pytest.approx(one.clearance_cap_s / 2, rel=0.05)


def test_bottleneck_is_narrow_link():
    # 0 → 1 wide, 1 → 2 narrow (exit 2). Narrow link must be the bottleneck.
    r = solve_flow(3, np.array([0, 1]), np.array([1, 2]), _arr(3000, 500), _arr(10, 10), _arr(10, 10), [2], {0: 500})
    assert r.bottleneck_arcs == [1]


def test_paths_conserve_vehicles():
    tails = np.array([0, 0, 1, 2, 3])
    heads = np.array([1, 2, 3, 3, 4])
    r = solve_flow(5, tails, heads, _arr(400, 400, 400, 400, 2000), _arr(10, 20, 10, 10, 5),
                   _arr(10, 20, 10, 10, 5), [4], {0: 300, 3: 50})
    by_origin = {}
    for p in r.paths:
        by_origin[p.origin] = by_origin.get(p.origin, 0) + p.vehicles
        assert tails[p.arcs[0]] == p.origin and heads[p.arcs[-1]] == 4
    assert by_origin == {0: 300, 3: 50}


def test_avoids_detour_when_it_doesnt_pay():
    # Fast route 20 s, detour 2000 s. Using the detour saves capacity time but costs far more
    # travel time, so the best total plan keeps everyone on the fast route.
    tails, heads = np.array([0, 0, 1, 2]), np.array([1, 2, 3, 3])
    tt = _arr(10, 1000, 10, 1000)
    r = solve_flow(4, tails, heads, _arr(600, 600, 600, 600), tt, tt, [3], {0: 100})
    assert r.arc_flow[0] == 100 and r.arc_flow[1] == 0


def test_uses_second_route_when_it_pays():
    # Two equally short routes: splitting halves capacity time, so both are used.
    tails, heads = np.array([0, 0, 1, 2]), np.array([1, 2, 3, 3])
    tt = _arr(10, 12, 10, 12)
    r = solve_flow(4, tails, heads, _arr(600, 600, 600, 600), tt, tt, [3], {0: 600})
    assert r.arc_flow[0] > 0 and r.arc_flow[1] > 0
    assert r.clearance_cap_s < 3600 * 0.75


def test_no_demand():
    r = solve_flow(2, np.array([0]), np.array([1]), _arr(600), _arr(60), _arr(60), [1], {})
    assert r.clearance_s == 0 and not r.paths


def test_unreachable_raises():
    with pytest.raises(RuntimeError):
        solve_flow(3, np.array([0]), np.array([1]), _arr(600), _arr(60), _arr(60), [2], {0: 10})
