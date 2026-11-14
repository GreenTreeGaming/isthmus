import numpy as np
import pytest

from engine import assumptions as A
from engine.flow import Path
from engine.sim import Group, simulate
from engine.waves import assign_waves, departure_s


def test_earliest_arrival_goes_first():
    paths = [Path(0, [0], 100, 60), Path(1, [0], 100, 60)]
    w = assign_waves([0, 1], {0: 5000.0, 1: 900.0}, {0: 60, 1: 60}, paths, {0}, np.array([600.0]))
    assert w[1] == 0 and w[0] >= 0
    assert w[1] <= w[0]


def test_waves_respect_capacity():
    # 600 veh/h × 10 min = 100 veh per wave on the shared exit link.
    paths = [Path(o, [0], 100, 60) for o in range(3)]
    w = assign_waves([0, 1, 2], {0: 700.0, 1: 800.0, 2: 900.0}, {o: 60 for o in range(3)}, paths, {0},
                     np.array([600.0]))
    assert sorted(w.values()) == [0, 1, 2]


def test_downstream_first_within_bucket():
    paths = [Path(0, [0], 100, 60), Path(1, [0], 100, 60)]
    w = assign_waves([0, 1], {0: 900.0, 1: 900.0}, {0: 400.0, 1: 50.0}, paths, {0}, np.array([600.0]))
    assert w[1] < w[0]


def test_departure_times():
    assert departure_s(0) == A.MOBILIZATION_S
    assert departure_s(2) == A.MOBILIZATION_S + 2 * A.WAVE_INTERVAL_S


def test_sim_single_link_queue():
    # 300 vehicles released in one step onto a 600 veh/h link → 30 min to drain.
    r = simulate(np.array([600.0]), np.array([60.0]), [Group([0], 300, 0)], release_window_s=30)
    assert r.exited == pytest.approx(300)
    assert r.clearance_s == pytest.approx(1800 + 60, abs=2 * A.SIM_STEP_S)
    assert r.peak_ratio[0] > 1
    assert not np.isnan(r.congested_at_s[0])


def test_sim_free_flow_no_congestion():
    r = simulate(np.array([1800.0, 1800.0]), np.array([30.0, 30.0]), [Group([0, 1], 10, 0)],
                 release_window_s=300)
    assert r.exited == pytest.approx(10)
    assert np.isnan(r.congested_at_s).all()
    assert r.clearance_s <= 300 + 60 + 2 * A.SIM_STEP_S


def test_sim_matches_flow_order_of_magnitude():
    # Two origins sharing a bottleneck: sim clearance should be close to capacity time.
    groups = [Group([0, 2], 200, 0), Group([1, 2], 200, 0)]
    r = simulate(np.array([2000.0, 2000.0, 800.0]), np.array([30.0, 30.0, 30.0]), groups,
                 release_window_s=60)
    expected = 400 / 800 * 3600
    assert expected * 0.9 < r.clearance_s < expected * 1.3
    assert r.peak_ratio[2] > r.peak_ratio[0] and r.peak_ratio[2] > r.peak_ratio[1]


def test_timeline_length_matches_steps():
    r = simulate(np.array([600.0]), np.array([60.0]), [Group([0], 50, 0)], release_window_s=30)
    assert len(r.timeline[0]) * r.step_s >= r.clearance_s
